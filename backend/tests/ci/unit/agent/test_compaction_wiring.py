"""compaction 事件翻译与 chat_service 接线单测。"""

from __future__ import annotations

from typing import Any

from apps.agent.pi.bridge import DeltaTracker, translate_all
from apps.agent.pi.rpc_client import PiEvent


def _translate(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return translate_all(PiEvent("event", raw), tracker=DeltaTracker())


class TestCompactionTranslation:
    def test_start_end_translated(self) -> None:
        assert _translate({"type": "compaction_start"}) == [{"type": "compaction", "phase": "start"}]
        assert _translate({"type": "compaction_end"}) == [{"type": "compaction", "phase": "end"}]

    def test_unknown_compaction_variant_dropped(self) -> None:
        """上游若加第三种变体（如 compaction_progress），不透传也不炸。"""
        assert _translate({"type": "compaction_progress"}) == []


class TestChatServiceImports:
    def test_stream_chat_accepts_skill_paths_wiring(self) -> None:
        """chat_service 门面必须仍重导出编排符号（接线断言：防将来重构丢线）。

        不真跑 stream_chat（要起 pi）；只验证符号存在——丢 import 会在运行时
        才炸。技能面不再靠 ``--skill`` 目录（那个已废弃的目录计算函数已删除），
        技能的送达改由 ``RunContext.skill_block`` 经系统提示注入，
        接线断言在 ``test_skill_delivery_wiring.py``。
        """
        import apps.agent.services.chat_service as chat_service

        assert hasattr(chat_service, "stream_chat")
        assert hasattr(chat_service, "_persist_compaction_message")
        assert hasattr(chat_service, "parse_context_usage")
