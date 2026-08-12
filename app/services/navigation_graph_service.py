from __future__ import annotations

from collections import deque
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.navigation_edge import NavigationEdge
from app.models.navigation_node import NavigationNode


class NavigationGraphService:
    """Source-scoped graph queries using an iterative breadth-first search."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def find_path(
        self, source_id: UUID, start: str | None, destination: str
    ) -> list[dict[str, Any]]:
        # Browser form fields commonly submit an empty string when the client
        # has no current-screen signal; treat that as absent context.
        start = start.strip() or None if start else None
        nodes = (
            self.db.query(NavigationNode)
            .filter(NavigationNode.knowledge_source_id == source_id)
            .all()
        )
        if not nodes:
            return []

        def matches(node: NavigationNode, value: str) -> bool:
            candidate = value.lower().strip()
            return candidate in {
                str(node.screen_id).lower(),
                str(node.route or "").lower(),
                str(node.title or "").lower(),
            }

        # The resolver has already selected the destination.  Graph traversal
        # must use that exact node and must never make a second, fuzzy choice.
        target = next((node for node in nodes if matches(node, destination)), None)
        if target is None:
            return []
        origin = next((node for node in nodes if start and matches(node, start)), None)
        if origin is None:
            # A missing current-screen signal is not a graph failure.  The UI
            # can navigate directly to this verified destination.
            return [self._serialize(target)] if start is None else []
        if origin.id == target.id:
            return [self._serialize(target)]
        edges = (
            self.db.query(NavigationEdge)
            .filter(NavigationEdge.knowledge_source_id == source_id)
            .all()
        )
        adjacency: dict[UUID, list[UUID]] = {}
        for edge in edges:
            adjacency.setdefault(edge.from_node_id, []).append(edge.to_node_id)
        queue: deque[UUID] = deque([origin.id])
        previous: dict[UUID, UUID | None] = {origin.id: None}
        while queue:
            current = queue.popleft()
            if current == target.id:
                break
            for neighbour in adjacency.get(current, []):
                if neighbour not in previous:
                    previous[neighbour] = current
                    queue.append(neighbour)
        if target.id not in previous:
            return []
        node_by_id = {node.id: node for node in nodes}
        path_ids: list[UUID] = []
        current: UUID | None = target.id
        while current is not None:
            path_ids.append(current)
            current = previous[current]
        return [self._serialize(node_by_id[node_id]) for node_id in reversed(path_ids)]

    def get_node(
        self,
        source_id: UUID,
        screen_id: str,
    ) -> dict[str, Any] | None:
        """Return one source-scoped navigation node by exact screen ID."""

        node = (
            self.db.query(NavigationNode)
            .filter(
                NavigationNode.knowledge_source_id == source_id,
                NavigationNode.screen_id == screen_id,
            )
            .first()
        )

        if node is None:
            return None

        return self._serialize(node)

    @staticmethod
    def _serialize(node: NavigationNode) -> dict[str, Any]:
        return {
            "id": node.screen_id,
            "route": node.route,
            "title": node.title,
            "module": node.module,
        }
