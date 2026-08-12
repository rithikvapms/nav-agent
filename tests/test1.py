from app.database.db import SessionLocal
from app.repositories.screen_repository import ScreenRepository
from app.services.navigation_resolver import NavigationResolver
from app.services.query_understanding import QueryUnderstanding

# Replace this with the knowledge_source_id of your current
# 300-screen connected graph.
KNOWLEDGE_SOURCE_ID = "dba6a001-f0a7-419a-b346-5543ff749960"


def main():
    db = SessionLocal()

    try:
        repository = ScreenRepository(db)
        resolver = NavigationResolver(repository)
        understanding = QueryUnderstanding()

        test_queries = [
            "report",
            "settings",
            "show me dashboard",
            "take me to users",
            "go to notifications",
        ]

        for query in test_queries:
            intent = understanding.detect_intent(query)

            resolved_query = understanding.retrieval_query(
                query,
                intent,
            )

            print(f"RAW QUERY: {query}")
            print(f"RESOLVER QUERY: {resolved_query}")

            result = resolver.resolve(
                query=resolved_query,
                knowledge_source_id=KNOWLEDGE_SOURCE_ID,
            )

            print("\n" + "=" * 60)
            print(f"QUERY: {query}")
            print(f"STATUS: {result.status}")

            if result.candidate:
                print(",MATCH:")
                print(f"  screen_id : {result.candidate.screen_id}")
                print(f"  title     : {result.candidate.title}")
                print(f"  module    : {result.candidate.module}")
                print(f"  route     : {result.candidate.route}")
                print(f"  score     : {result.candidate.score}")

            if result.candidates:
                print("CANDIDATES:")
                for candidate in result.candidates[:5]:
                    print(
                        f"  {candidate.score:.3f} | "
                        f"{candidate.screen_id} | "
                        f"{candidate.title} | "
                        f"{candidate.route}"
                    )

    finally:
        db.close()


if __name__ == "__main__":
    main()
