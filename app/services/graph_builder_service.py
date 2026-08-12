from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.navigation_edge import NavigationEdge
from app.models.navigation_node import NavigationNode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphBuildResult:
    source_id: UUID
    nodes_created: int
    edges_created: int
    unresolved_parent_routes: int
    unresolved_child_routes: int
    unresolved_next_routes: int
    invalid_screens: int
    duplicate_screen_ids: int
    duplicate_routes: int


class GraphBuilderService:
    """
    Builds a source-scoped navigation graph.

    Transaction ownership:
        This service NEVER commits or rolls back the outer transaction.

        The caller owns the transaction.

    The graph builder:
        - validates the navigation source
        - replaces the graph for one knowledge source
        - creates real screen nodes
        - creates edges only between existing nodes
        - flushes changes so database constraints are checked
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def build(
        self,
        data: dict[str, Any],
        source_id: UUID,
    ) -> tuple[int, int]:

        result = self.build_detailed(data, source_id)

        logger.info(
            "Navigation graph built | "
            "source=%s nodes=%d edges=%d "
            "unresolved_parent=%d unresolved_child=%d "
            "unresolved_next=%d invalid=%d "
            "duplicate_screen_ids=%d duplicate_routes=%d",
            result.source_id,
            result.nodes_created,
            result.edges_created,
            result.unresolved_parent_routes,
            result.unresolved_child_routes,
            result.unresolved_next_routes,
            result.invalid_screens,
            result.duplicate_screen_ids,
            result.duplicate_routes,
        )

        return result.nodes_created, result.edges_created

    def build_detailed(
        self,
        data: dict[str, Any],
        source_id: UUID,
    ) -> GraphBuildResult:

        screens = self._validate_payload(data)

        logger.info(
            "Navigation graph ingestion started | source=%s screens=%d",
            source_id,
            len(screens),
        )

        try:
            normalized_screens = self._normalize_screens(screens)

            # ---------------------------------------------------------
            # Delete the existing graph for this source.
            #
            # IMPORTANT:
            # This is NOT committed here.
            # If anything fails later, the outer transaction rolls
            # everything back.
            # ---------------------------------------------------------

            self._delete_existing_graph(source_id)

            # ---------------------------------------------------------
            # Create nodes
            # ---------------------------------------------------------

            nodes, route_index, duplicate_routes = self._create_nodes(
                normalized_screens,
                source_id,
            )

            # Node IDs are required by NavigationEdge.
            self.db.flush()

            # ---------------------------------------------------------
            # Create edges
            # ---------------------------------------------------------

            (
                edges_created,
                unresolved_parent_routes,
                unresolved_child_routes,
                unresolved_next_routes,
            ) = self._create_edges(
                normalized_screens,
                nodes,
                route_index,
                source_id,
            )

            # Make sure edge FK/unique constraints are checked now.
            #
            # Still NOT committed.
            self.db.flush()

            result = GraphBuildResult(
                source_id=source_id,
                nodes_created=len(nodes),
                edges_created=edges_created,
                unresolved_parent_routes=unresolved_parent_routes,
                unresolved_child_routes=unresolved_child_routes,
                unresolved_next_routes=unresolved_next_routes,
                invalid_screens=0,
                duplicate_screen_ids=0,
                duplicate_routes=duplicate_routes,
            )

            logger.info(
                "Navigation graph ingestion completed | "
                "source=%s nodes=%d edges=%d",
                source_id,
                result.nodes_created,
                result.edges_created,
            )

            return result

        except (ValueError, SQLAlchemyError):
            logger.exception(
                "Navigation graph build failed | source=%s",
                source_id,
            )

            # DO NOT rollback here.
            #
            # The outer transaction owner is responsible for rollback.
            raise

        except Exception:
            logger.exception(
                "Unexpected navigation graph build failure | source=%s",
                source_id,
            )

            # DO NOT rollback here.
            raise

    # ================================================================
    # Validation
    # ================================================================

    @staticmethod
    def _validate_payload(
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:

        if not isinstance(data, dict):
            raise ValueError(
                "Navigation data must be a JSON object."
            )

        screens = data.get("screens")

        if not isinstance(screens, list):
            raise ValueError(
                "JSON must contain a 'screens' array."
            )

        if not screens:
            raise ValueError(
                "Navigation graph cannot be built from an empty screens array."
            )

        for index, screen in enumerate(screens):

            if not isinstance(screen, dict):
                raise ValueError(
                    f"Screen at index {index} must be an object."
                )

        return screens

    @staticmethod
    def _normalize_screens(
        screens: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        normalized: list[dict[str, Any]] = []

        seen_screen_ids: set[str] = set()

        for index, screen in enumerate(screens):

            screen_id = str(
                screen.get("screen_id") or ""
            ).strip()

            if not screen_id:
                raise ValueError(
                    f"Screen at index {index} is missing 'screen_id'."
                )

            if screen_id in seen_screen_ids:
                raise ValueError(
                    f"Duplicate screen_id detected: {screen_id}"
                )

            seen_screen_ids.add(screen_id)

            route = screen.get("route")

            route = (
                str(route).strip()
                if route is not None
                else None
            )

            title = screen.get("title")

            title = (
                str(title).strip()
                if title is not None
                else None
            )

            module = screen.get("module")

            module = (
                str(module).strip()
                if module is not None
                else None
            )

            navigation = screen.get("navigation")

            if navigation is None:
                navigation = {}

            if not isinstance(navigation, dict):
                raise ValueError(
                    f"Navigation metadata for screen "
                    f"'{screen_id}' must be an object."
                )

            child_routes = navigation.get(
                "child_routes"
            ) or []

            if not isinstance(child_routes, list):
                raise ValueError(
                    f"'child_routes' for screen "
                    f"'{screen_id}' must be an array."
                )

            normalized_child_routes = [
                str(route_value).strip()
                for route_value in child_routes
                if route_value is not None
                and str(route_value).strip()
            ]

            normalized.append(
                {
                    "screen_id": screen_id,
                    "route": route,
                    "title": title,
                    "module": module,
                    "navigation": {
                        "parent_route": _normalize_route(
                            navigation.get("parent_route")
                        ),
                        "next_route": _normalize_route(
                            navigation.get("next_route")
                        ),
                        "child_routes": normalized_child_routes,
                    },
                }
            )

        return normalized

    # ================================================================
    # Nodes
    # ================================================================

    def _create_nodes(
        self,
        screens: list[dict[str, Any]],
        source_id: UUID,
    ) -> tuple[
        dict[str, NavigationNode],
        dict[str, NavigationNode],
        int,
    ]:

        nodes: dict[str, NavigationNode] = {}
        route_index: dict[str, NavigationNode] = {}

        duplicate_routes = 0

        for screen in screens:

            screen_id = screen["screen_id"]
            route = screen["route"]

            node = NavigationNode(
                knowledge_source_id=source_id,
                screen_id=screen_id,
                route=route,
                title=screen["title"],
                module=screen["module"],
            )

            self.db.add(node)

            nodes[screen_id] = node

            if route:

                normalized_route = _normalize_route(route)

                if normalized_route in route_index:
                    duplicate_routes += 1

                    raise ValueError(
                        "Duplicate route detected for "
                        f"navigation source: {normalized_route}"
                    )

                route_index[normalized_route] = node

        return nodes, route_index, duplicate_routes

    # ================================================================
    # Edges
    # ================================================================

    def _create_edges(
        self,
        screens: list[dict[str, Any]],
        nodes: dict[str, NavigationNode],
        route_index: dict[str, NavigationNode],
        source_id: UUID,
    ) -> tuple[int, int, int, int]:

        edge_keys: set[
            tuple[str, str, str]
        ] = set()

        edges_created = 0
        unresolved_parent_routes = 0
        unresolved_child_routes = 0
        unresolved_next_routes = 0

        for screen in screens:

            source = nodes[
                screen["screen_id"]
            ]

            navigation = screen["navigation"]

            # --------------------------------------------------------
            # Parent
            # --------------------------------------------------------

            parent_route = navigation[
                "parent_route"
            ]

            if parent_route:

                target = route_index.get(
                    parent_route
                )

                if target is None:

                    unresolved_parent_routes += 1

                    logger.warning(
                        "Unresolved parent route | "
                        "source=%s screen=%s parent_route=%s",
                        source_id,
                        source.screen_id,
                        parent_route,
                    )

                else:

                    if self._add_edge(
                        source_node=target,
                        target_node=source,
                        relationship="child_route",
                        source_id=source_id,
                        edge_keys=edge_keys,
                    ):
                        edges_created += 1

            # --------------------------------------------------------
            # Children
            # --------------------------------------------------------

            for child_route in navigation[
                "child_routes"
            ]:

                target = route_index.get(
                    _normalize_route(child_route)
                )

                if target is None:

                    unresolved_child_routes += 1

                    logger.warning(
                        "Unresolved child route | "
                        "source=%s screen=%s child_route=%s",
                        source_id,
                        source.screen_id,
                        child_route,
                    )

                    continue

                if self._add_edge(
                    source_node=source,
                    target_node=target,
                    relationship="child_route",
                    source_id=source_id,
                    edge_keys=edge_keys,
                ):
                    edges_created += 1

            # --------------------------------------------------------
            # Next
            # --------------------------------------------------------

            next_route = navigation[
                "next_route"
            ]

            if next_route:

                target = route_index.get(
                    next_route
                )

                if target is None:

                    unresolved_next_routes += 1

                    logger.warning(
                        "Unresolved next route | "
                        "source=%s screen=%s next_route=%s",
                        source_id,
                        source.screen_id,
                        next_route,
                    )

                else:

                    if self._add_edge(
                        source_node=source,
                        target_node=target,
                        relationship="next_route",
                        source_id=source_id,
                        edge_keys=edge_keys,
                    ):
                        edges_created += 1

        return (
            edges_created,
            unresolved_parent_routes,
            unresolved_child_routes,
            unresolved_next_routes,
        )

    def _add_edge(
        self,
        source_node: NavigationNode,
        target_node: NavigationNode,
        relationship: str,
        source_id: UUID,
        edge_keys: set[tuple[str, str, str]],
    ) -> bool:

        if source_node.id == target_node.id:

            logger.debug(
                "Skipping self-referencing navigation edge | screen=%s",
                source_node.screen_id,
            )

            return False

        key = (
            str(source_node.id),
            str(target_node.id),
            relationship,
        )

        if key in edge_keys:
            return False

        self.db.add(
            NavigationEdge(
                knowledge_source_id=source_id,
                from_node_id=source_node.id,
                to_node_id=target_node.id,
                relationship=relationship,
                weight=1.0,
            )
        )

        edge_keys.add(key)

        return True

    # ================================================================
    # Existing graph cleanup
    # ================================================================

    def _delete_existing_graph(
        self,
        source_id: UUID,
    ) -> None:

        self.db.query(
            NavigationEdge
        ).filter(
            NavigationEdge.knowledge_source_id == source_id
        ).delete(
            synchronize_session=False
        )

        self.db.query(
            NavigationNode
        ).filter(
            NavigationNode.knowledge_source_id == source_id
        ).delete(
            synchronize_session=False
        )


def _normalize_route(
    value: Any,
) -> str | None:

    if value is None:
        return None

    route = str(value).strip()

    if not route:
        return None

    if route != "/":
        route = route.rstrip("/")

    return route