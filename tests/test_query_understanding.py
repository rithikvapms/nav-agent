from app.services.query_understanding import QueryUnderstanding


def test_domain_typo_is_corrected():
    understanding = QueryUnderstanding(["authentication", "permissions", "dashboard"])
    normalized, corrections = understanding.normalize("opne authentcation permisions")

    assert normalized == "open authentication permissions"
    assert corrections == [
        ("opne", "open"),
        ("authentcation", "authentication"),
        ("permisions", "permissions"),
    ]


def test_intent_detection_prefers_navigation_for_screen_request():
    assert QueryUnderstanding().detect_intent("plese take me to authntication") == "navigate"
    assert QueryUnderstanding().detect_intent("hello there") == "chat"


def test_mixed_conversation_and_navigation_prefers_navigation():
    understanding = QueryUnderstanding(["authentication"])
    question = "Hi, how are you? Can you take me to authentication?"

    assert understanding.detect_intent(question) == "navigate"
    assert understanding.retrieval_query(question, "navigate") == "take me to authentication?"
