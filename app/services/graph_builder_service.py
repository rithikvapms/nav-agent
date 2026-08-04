from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.navigation_edge import NavigationEdge
from app.models.navigation_node import NavigationNode

logger = logging.getLogger(__name__)


class GraphBuilderService:
    """Builds a source-scoped navigation graph from the uploaded screen JSON."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def build(self, data: dict[str, Any], source_id: UUID) -> tuple[int, int]:
        screens = data.get("screens")
        if not isinstance(screens, list):
            raise ValueError("JSON must contain a screens array")

        self.db.query(NavigationEdge).filter(NavigationEdge.knowledge_source_id == source_id).delete(synchronize_session=False)
        self.db.query(NavigationNode).filter(NavigationNode.knowledge_source_id == source_id).delete(synchronize_session=False)
        nodes: dict[str, NavigationNode] = {}
        routes: dict[str, NavigationNode] = {}
        for screen in screens:
            screen_id = str(screen.get("screen_id", "")).strip()
            if not screen_id:
                raise ValueError("Every screen must have a screen_id")
            node = NavigationNode(
                knowledge_source_id=source_id, screen_id=screen_id,
                route=screen.get("route"), title=screen.get("title"), module=screen.get("module"),
            )
            self.db.add(node)
            nodes[screen_id] = node
            if screen.get("route"):
                routes[str(screen["route"])] = node
        self.db.flush()

        edges: set[tuple[str, str]] = set()
        def add_edge(source: NavigationNode, target: NavigationNode, relationship: str) -> None:
            if source.id != target.id and (str(source.id), str(target.id)) not in edges:
                self.db.add(NavigationEdge(
                    knowledge_source_id=source_id, from_node_id=source.id, to_node_id=target.id,
                    relationship=relationship, weight=1.0,
                ))
                edges.add((str(source.id), str(target.id)))

        for screen in screens:
            source = nodes[str(screen["screen_id"])]
            navigation = screen.get("navigation") or {}
            for key in ("parent_route", "route", "next_route"):
                value = navigation.get(key)
                if value and value in routes and key != "route":
                    add_edge(source, routes[value], key)
            for value in navigation.get("child_routes", []) or []:
                if value in routes:
                    add_edge(source, routes[value], "child_route")
            parent = navigation.get("parent_route")
            if parent in routes:
                add_edge(routes[parent], source, "child_route")
        self.db.commit()
        logger.info("Navigation graph built | source=%s nodes=%d edges=%d", source_id, len(nodes), len(edges))
        return len(nodes), len(edges)
