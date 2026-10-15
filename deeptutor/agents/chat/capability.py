"""Agentic chat capability."""

from __future__ import annotations

import asyncio
import re

from deeptutor.agents.chat.agentic_pipeline import CHAT_OPTIONAL_TOOLS, AgenticChatPipeline
from deeptutor.core.capability_protocol import CapabilityManifest, TurnCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.runtime.request_contracts import get_capability_request_schema
from deeptutor.runtime.stream_bus import StreamBus

_OGE_SCORE_COMMENT = re.compile(
    r"(?:\A|\n)<!--\s*OGE_SCORE:\s*(?:(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*;\s*attempt=([A-Za-z0-9_-]{1,100})|manual_review)\s*-->\s*\Z",
    re.IGNORECASE,
)


class ChatCapability(TurnCapability):
    manifest = CapabilityManifest(
        name="chat",
        description=(
            "Agentic chat: an exploring agent loop with tools, followed by "
            "a respond stage that streams the answer."
        ),
        stages=["exploring", "responding"],
        tools_used=CHAT_OPTIONAL_TOOLS,
        cli_aliases=["chat"],
        request_schema=get_capability_request_schema("chat"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        pipeline = AgenticChatPipeline(language=context.language)
        store = None
        entry_id = self._single_question_reference(context)
        turn_id = context.runtime.turn_id or str(context.metadata.get("turn_id") or "")
        if entry_id:
            from deeptutor.services.practice.storage import PracticeStore
            from deeptutor.services.session import get_sqlite_session_store

            store = get_sqlite_session_store()
            entry = await store.get_notebook_entry(entry_id)
            if entry and entry.get("checking_mode") == "model":
                criteria = await asyncio.to_thread(
                    PracticeStore(store.db_path).question_criteria, entry_id
                )
                if turn_id:
                    context.user_message += self._oge_grading_instruction(
                        entry, criteria, turn_id
                    )
        result = await pipeline.run(context, stream)
        if store and entry_id and context.session_id:
            content = str((result or {}).get("response") or "")
            match = _OGE_SCORE_COMMENT.search(content)
            if match and match.group(1) and match.group(2) and match.group(3) == turn_id:
                try:
                    await asyncio.to_thread(
                        PracticeStore(store.db_path).record_model_score,
                        entry_id,
                        turn_id,
                        float(match.group(1)),
                        float(match.group(2)),
                        context.session_id,
                    )
                except (LookupError, ValueError):
                    pass

    @staticmethod
    def _single_question_reference(context: UnifiedContext) -> int | None:
        references = context.metadata.get("question_notebook_references") or []
        if not isinstance(references, list) or len(references) != 1:
            return None
        value = references[0]
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        text = str(value or "").strip()
        return int(text) if text.isdigit() and int(text) > 0 else None

    @staticmethod
    def _oge_grading_instruction(entry: dict, criteria: list[dict], turn_id: str) -> str:
        maximum = float(entry["max_score"] or 0)
        criteria_lines = "\n".join(
            f"- {item['score']}: {item['text']} (source: {item['source']}; scope: {item['scope']})"
            for item in criteria
        ) or "(none)"
        criteria_only = not str(entry.get("correct_answer") or "").strip() and bool(criteria)
        grading_basis = (
            "This verified question is graded by its sourced criteria without a reference answer. "
            "Independently solve the exact question and evaluate the student's reasoning against "
            "those criteria. State that the score is criteria-based without a reference solution. "
            "If you cannot justify the proof or calculation, request manual review. "
            if criteria_only and entry.get("reference_status") in {"verified", "confirmed"}
            else "Use this exact question, its verified reference, and these criteria. If the reference "
                 "is missing, unverified, or belongs to another question, request manual review. "
        )
        # Position 22 answers arrive as coordinates, not as a drawing: the student
        # lists each piece by its type and defining points. Without this note the
        # grader has no way to tell a described graph from a bare numeric answer,
        # and the criterion's split between the graph and the parameter values
        # cannot be applied.
        graph_basis = (
            "This answer describes a graph by coordinates. The student lists every piece with its "
            "type and defining points (two points for a line, three for a parabola or hyperbola), "
            "then the punctured points, then the parameter values. Rebuild each piece from its "
            "points, compare the result with the graph of your own solution, and apply the "
            "criterion: a correct graph with correct parameter values earns the full score, a "
            "correct graph alone earns one point, anything else earns zero. "
            if str(entry.get("answer_format") or "") == "graph_and_parameter"
            else ""
        )
        return (
            "\n\n[Official OGE grading context for the single selected question]\n"
            f"Question: {entry['question']}\nReference answer: {entry['correct_answer'] or '(none)'}\n"
            f"Reference status: {entry.get('reference_status') or '(none)'}\n"
            f"Maximum score: {maximum:g}\nCriteria:\n{criteria_lines}\n"
            "If the user explicitly asks you to grade a solution: "
            f"{grading_basis}{graph_basis}"
            "When manual review is needed, end with <!--OGE_SCORE: manual_review--> . "
            "Otherwise give a score within the maximum "
            f"and end with <!--OGE_SCORE: score / {maximum:g}; attempt={turn_id}--> . "
            "Do not emit either "
            "marker when the user did not ask for grading.\n"
        )
