import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.services.navigation_agent import APMSNavigationAgent
from app.services.navigation_resolver import NavigationResolver
from app.services.query_understanding import QueryUnderstanding


class FakeRepository:
    def __init__(self, nodes):
        self.nodes = nodes

    def find_navigation_node(self, _, **criteria):
        value = next(value for value in criteria.values() if value is not None)
        field = next(key for key, value in criteria.items() if value is not None)
        return [node for node in self.nodes if getattr(node, field).lower() == value]

    def search_navigation_nodes(self, _, query_text, limit=10):
        query = query_text.lower()
        return [node for node in self.nodes if query in " ".join(
            str(getattr(node, field) or "") for field in ("screen_id", "title", "module", "route")
        ).lower()][:limit]


class NavigationCoreTests(unittest.TestCase):
    def setUp(self):
        self.source_id = uuid4()
        self.nodes = [
            SimpleNamespace(screen_id="dashboard_002", title="Dashboard Screen 002", module="Dashboard", route="/dashboard/002"),
            SimpleNamespace(screen_id="dashboard_218", title="Dashboard Screen 218", module="Dashboard", route="/dashboard/218"),
        ]

    def test_ambiguous_module_never_selects_arbitrary_screen(self):
        result = NavigationResolver(FakeRepository(self.nodes)).resolve("dashboard", self.source_id)
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual({item.screen_id for item in result.candidates}, {"dashboard_002", "dashboard_218"})

    def test_exact_screen_id_resolves(self):
        result = NavigationResolver(FakeRepository(self.nodes)).resolve("Dashboard Screen 218", self.source_id)
        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.candidate.screen_id, "dashboard_218")

    def test_disconnected_current_screen_is_not_reported_as_success(self):
        agent = APMSNavigationAgent.__new__(APMSNavigationAgent)
        agent.knowledge_source_id = self.source_id
        agent.graph = SimpleNamespace(find_path=lambda *_: [])
        candidate = SimpleNamespace(screen_id="dashboard_218", title="Dashboard Screen 218", module="Dashboard", route="/dashboard/218", score=1.0)
        answer = agent._build_navigation_answer(candidate, current_screen="home")
        self.assertEqual(answer.answer["status"], "navigation_unavailable")

    def test_navigation_verbs_are_removed_without_mutating_target(self):
        understanding = QueryUnderstanding()
        for request, target in (
            ("bring me to Dashboard Screen 218", "Dashboard Screen 218"),
            ("move to settings", "settings"),
            ("access reports", "reports"),
        ):
            self.assertEqual(understanding.detect_intent(request), "navigate")
            self.assertEqual(understanding.retrieval_query(request, "navigate"), target)


if __name__ == "__main__":
    unittest.main()
