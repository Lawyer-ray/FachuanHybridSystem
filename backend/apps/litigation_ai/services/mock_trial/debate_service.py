"""辩论模拟 Service."""

from __future__ import annotations

import logging
from typing import Any

from apps.litigation_ai.chains.mock_trial_chains import (
    DebateChain,
    DebateResult,
    DisputeFocusChain,
    DisputeFocusResult,
)

logger = logging.getLogger("apps.litigation_ai")


class DebateService:
    """辩论模拟：围绕争议焦点进行多轮辩论."""

    async def analyze_focuses(
        self, *, case_info: dict[str, Any], evidence_text: str
    ) -> DisputeFocusResult:
        """归纳争议焦点."""
        chain = DisputeFocusChain()
        return await chain.arun(case_info=case_info, evidence_text=evidence_text)

    async def debate_turn(
        self,
        *,
        case_info: dict[str, Any],
        focus: dict[str, Any],
        user_argument: str,
        history: list[dict[str, str]],
        difficulty: str = "medium",
    ) -> DebateResult:
        """一轮辩论：用户发言 → AI 反驳."""
        chain = DebateChain(difficulty=difficulty)
        return await chain.arun(
            case_info=case_info,
            focus=focus,
            user_argument=user_argument,
            history=history,
        )
