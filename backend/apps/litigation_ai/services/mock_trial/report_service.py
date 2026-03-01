"""模拟庭审报告生成 Service."""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async

logger = logging.getLogger("apps.litigation_ai")


class MockTrialReportService:
    """从 session metadata 提取并格式化各模式的报告."""

    async def get_report(self, session_id: str) -> dict[str, Any]:
        from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository

        repo = LitigationSessionRepository()
        metadata = await repo.get_metadata(session_id)
        mode = metadata.get("mock_trial_mode", "")

        if mode == "judge":
            return self._judge_report(metadata)
        elif mode == "cross_exam":
            return self._cross_exam_report(metadata)
        elif mode == "debate":
            return self._debate_report(metadata)
        return {"mode": mode, "status": "no_data"}

    def _judge_report(self, metadata: dict[str, Any]) -> dict[str, Any]:
        report = metadata.get("judge_report", {})
        return {"mode": "judge", "report": report, "status": "complete" if report else "no_data"}

    def _cross_exam_report(self, metadata: dict[str, Any]) -> dict[str, Any]:
        results = metadata.get("cross_exam_results", [])
        total = len(results)
        high = sum(1 for r in results if r.get("opinion", {}).get("risk_level") == "high")
        medium = sum(1 for r in results if r.get("opinion", {}).get("risk_level") == "medium")
        return {
            "mode": "cross_exam",
            "status": "complete" if results else "no_data",
            "summary": {"total": total, "high_risk": high, "medium_risk": medium, "low_risk": total - high - medium},
            "results": results,
        }

    def _debate_report(self, metadata: dict[str, Any]) -> dict[str, Any]:
        history = metadata.get("debate_history", [])
        focus = metadata.get("debate_selected_focus", {})
        rounds = len([h for h in history if h.get("role") == "user"])
        return {
            "mode": "debate",
            "status": "complete" if history else "no_data",
            "focus": focus,
            "rounds": rounds,
            "history": history,
        }
