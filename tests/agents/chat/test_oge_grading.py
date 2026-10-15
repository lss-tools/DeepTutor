import asyncio

from deeptutor.agents.chat import capability as chat_capability
from deeptutor.agents.chat.capability import ChatCapability, _OGE_SCORE_COMMENT
from deeptutor.core.context import TurnRuntimeContext, UnifiedContext
from deeptutor.runtime.stream_bus import StreamBus


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


def test_chat_records_grade_from_current_pipeline_result(monkeypatch, tmp_path):
    turn_id = "turn_123"
    session_id = "session_123"
    calls = []

    class Store:
        db_path = tmp_path / "chat_history.db"

        async def get_notebook_entry(self, entry_id):
            assert entry_id == 17
            return {
                "checking_mode": "model",
                "question": "Solve x² = 4",
                "correct_answer": "−2; 2",
                "reference_status": "verified",
                "max_score": 2,
            }

        async def get_last_message(self, *_args, **_kwargs):
            raise AssertionError("The current assistant message is not persisted yet")

    class PracticeStore:
        def __init__(self, db_path):
            assert db_path == Store.db_path

        def question_criteria(self, entry_id):
            assert entry_id == 17
            return [{"score": 2, "text": "Correct", "source": "FIPI", "scope": "position 20"}]

        def record_model_score(self, *args):
            calls.append(args)

    class Pipeline:
        def __init__(self, **_kwargs):
            pass

        async def run(self, _context, _stream):
            return {
                "response": f"Full credit.\n<!--OGE_SCORE: 2 / 2; attempt={turn_id}-->"
            }

    monkeypatch.setattr(chat_capability, "AgenticChatPipeline", Pipeline)
    monkeypatch.setattr("deeptutor.services.practice.storage.PracticeStore", PracticeStore)
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: Store())

    context = UnifiedContext(
        session_id=session_id,
        metadata={"question_notebook_references": [17]},
        runtime=TurnRuntimeContext(turn_id=turn_id),
    )
    asyncio.run(ChatCapability().run(context, StreamBus()))

    assert calls == [(17, turn_id, 2.0, 2.0, session_id)]


def test_verified_criteria_only_grading_uses_criteria_without_demanding_a_reference():
    entry = {"question": "Prove it", "correct_answer": "", "reference_status": "verified", "max_score": 2}
    criteria = [{"score": 2, "text": "A justified proof", "source": "FIPI", "scope": "24"}]
    instruction = ChatCapability._oge_grading_instruction(entry, criteria, "turn_criteria")
    assert "graded by its sourced criteria without a reference answer" in instruction
    assert "Independently solve" in instruction
    unverified = ChatCapability._oge_grading_instruction({**entry, "reference_status": "unchecked"}, criteria, "turn_unverified")
    assert "graded by its sourced criteria without a reference answer" not in unverified
    assert "request manual review" in unverified
