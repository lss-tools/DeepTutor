from __future__ import annotations

from typing import Any

import pytest

from deeptutor.agents.question.agents.followup_agent import FollowupAgent


class CaptureFollowupAgent(FollowupAgent):
    """``FollowupAgent`` subclass that records every system prompt sent to
    the LLM (so the language-directive injection can be asserted), while
    short-circuiting the actual network call."""

    def __init__(self, language: str = "zh") -> None:
        self.language = language
        self.prompts: dict[str, Any] = {
            "system": "Followup system",
            "answer_followup": (
                "Question context:\n{question_context}\n\n"
                "Conversation history:\n{history_context}\n\n"
                "User follow-up:\n{user_message}\n"
            ),
        }
        self.captured_system_prompts: list[str] = []
        self.captured_user_prompts: list[str] = []

    async def stream_llm(self, **kwargs):  # type: ignore[override]
        self.captured_system_prompts.append(str(kwargs["system_prompt"]))
        self.captured_user_prompts.append(str(kwargs["user_prompt"]))
        yield "已回答"


@pytest.mark.asyncio
async def test_followup_agent_appends_language_directive_to_system_prompt() -> None:
    agent = CaptureFollowupAgent(language="zh")

    reply = await agent.process(
        user_message="为什么这题是这个答案？",
        question_context={
            "question_id": "q_1",
            "question_type": "choice",
            "question": "矩阵乘法什么时候有定义？",
            "correct_answer": "当内维度一致时。",
            "explanation": "矩阵 A 的列数必须等于矩阵 B 的行数。",
        },
        history_context="",
    )

    assert reply == "已回答"
    assert agent.captured_system_prompts
    assert "Followup system" in agent.captured_system_prompts[0]
    assert "请严格使用中文（简体）" in agent.captured_system_prompts[0]


@pytest.mark.asyncio
async def test_followup_agent_uses_only_verified_oge_criteria_for_scoring() -> None:
    agent = CaptureFollowupAgent(language="en")
    await agent.process(
        user_message="Please grade my solution.",
        question_context={
            "question_id": "oge-20",
            "question_type": "short_answer",
            "question": "Solve x² = 4",
            "user_answer": "x=2",
            "correct_answer": "x=−2 or x=2",
            "explanation": "The roots are −2 and 2.",
            "checking_mode": "model",
            "reference_status": "verified",
            "max_score": 2,
            "criteria": [
                {
                    "score": 2,
                    "text": "Both roots found",
                    "source": "FIPI",
                    "scope": "position 20",
                }
            ],
        },
    )
    prompt = agent.captured_user_prompts[0]
    assert "Do not use your general knowledge" in prompt
    assert "Both roots found" in prompt
    assert "[[OGE_SCORE: score / 2]]" in prompt


@pytest.mark.asyncio
async def test_followup_agent_refuses_scoring_without_verified_criteria() -> None:
    agent = CaptureFollowupAgent(language="en")
    await agent.process(
        user_message="Please grade my solution.",
        question_context={"question": "Q", "checking_mode": "model", "criteria": []},
    )
    assert "Do not assign a score" in agent.captured_user_prompts[0]
    assert "[[OGE_SCORE: manual_review]]" in agent.captured_user_prompts[0]
