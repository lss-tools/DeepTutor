from deeptutor.agents.chat.capability import ChatCapability, _OGE_SCORE_COMMENT
from deeptutor.core.context import UnifiedContext


def test_chat_score_marker_accepts_only_a_terminal_score_comment():
    match = _OGE_SCORE_COMMENT.search(
        "The solution earns full credit.\n<!--OGE_SCORE: 2 / 2; attempt=turn_123-->")
    assert match is not None
    assert match.group(1) == "2"
    assert match.group(2) == "2"
    assert match.group(3) == "turn_123"
    assert _OGE_SCORE_COMMENT.search("<!--OGE_SCORE: manual_review-->").group(1) is None
    assert _OGE_SCORE_COMMENT.search("<!--OGE_SCORE: 9 / 2--> trailing text") is None


def test_chat_grading_requires_one_selected_question():
    context = UnifiedContext(metadata={"question_notebook_references": [17]})
    assert ChatCapability._single_question_reference(context) == 17
    context.metadata["question_notebook_references"] = [17, 18]
    assert ChatCapability._single_question_reference(context) is None


def test_chat_grading_instruction_uses_the_question_criteria():
    prompt = ChatCapability._oge_grading_instruction(
        {
            "question": "Solve x² = 4",
            "correct_answer": "−2; 2",
            "reference_status": "verified",
            "max_score": 2,
        },
        [{"score": 1, "text": "Finds one root", "source": "FIPI", "scope": "position 20"}],
        "turn_123",
    )
    assert "verified reference" in prompt
    assert "Finds one root" in prompt
    assert "<!--OGE_SCORE: score / 2; attempt=turn_123-->" in prompt
