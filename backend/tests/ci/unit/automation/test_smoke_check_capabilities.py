"""``smoke_check`` 的部署能力自检段落（``_check_deployment_capabilities``）的输出契约。

只验 stdout：不可用时逐条打 note、全可用时打一行 ✅、``--skip-capabilities`` 时两条都不打，
以及**缺 key 永远不把命令变成失败**（退出码不反映配置选择）。能力判据本身在
``tests/ci/unit/pdf_splitting/test_deployment_capabilities.py``，这里把 ``deployment_capabilities``
整个换掉——顺带证明这道检查只用它的返回值。

**不许真跑别的冒烟步骤**：migrate / 建超管 / admin 页面 / 上传接口 / django-q 全部换掉
（沿用 ``test_smoke_check_safety.py`` 里的替身做法），否则这条用例会去建表、起子进程。
"""

from __future__ import annotations

from io import StringIO
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command

from apps.automation.management.commands import smoke_check
from apps.pdf_splitting.services import capabilities

#: 一条真实 note（与 ``capabilities.NOTE_CLOUD_ALL_UNAVAILABLE`` 同文案）。
#: 刻意写成字面量而不是引用常量：这里要证明的是「命令把 note 原样打出来」，
#: 引用常量会让「命令打错文案」这类回归通过。
_UNAVAILABLE_NOTE = (
    "云端取字全部不可用：MinerU / Textin 未启用，DeepSeek 未配 Key。当前只能走本地 OCR（生僻字与印章易错）。"
)

_SKIP_EVERYTHING: dict[str, Any] = {
    "yes": True,
    "skip_admin": True,
    "skip_upload": True,
    "skip_websocket": True,
    "skip_q": True,
    "skip_disk": True,
}


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 handle 里除能力自检以外的每一步都换成替身（migrate / 超管 / HTTP 客户端）。"""
    monkeypatch.setattr(smoke_check, "call_command", MagicMock())
    monkeypatch.setattr(smoke_check, "Client", MagicMock())
    monkeypatch.setattr(smoke_check.Command, "_ensure_smoke_superuser", lambda self: (MagicMock(), False))


def _stub_capabilities(monkeypatch: pytest.MonkeyPatch, notes: list[str]) -> None:
    """钉住自检结果：``notes`` 为空即「全可用」。"""
    stub: dict[str, Any] = {
        "judge": {"enabled": not notes, "reason": "enabled"},
        "engines": {"mineru": True, "textin": True, "deepseek": True},
        "notes": list(notes),
    }
    monkeypatch.setattr(capabilities, "deployment_capabilities", lambda: stub)


def _run(monkeypatch: pytest.MonkeyPatch, *, notes: list[str], skip_capabilities: bool = False) -> str:
    """跑一遍 ``smoke_check``（其余检查全跳过），返回 stdout 全文。"""
    _stub_capabilities(monkeypatch, notes)
    out = StringIO()
    call_command(
        "smoke_check",
        stdout=out,
        **{**_SKIP_EVERYTHING, "skip_capabilities": skip_capabilities},
    )
    return out.getvalue()


def test_unavailable_capabilities_are_printed_as_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    """不可用 → 每条 note 一行 ⚠️，且不打那一行 ✅。"""
    text = _run(monkeypatch, notes=[_UNAVAILABLE_NOTE])

    assert _UNAVAILABLE_NOTE in text
    assert "⚠️" in text
    assert "✅ 部署能力" not in text


def test_all_available_prints_single_ok_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """全可用 → 恰好一行 ✅（不打任何 ⚠️）。"""
    text = _run(monkeypatch, notes=[])

    assert "✅ 部署能力：云端取字 / 分歧裁定均可用" in text
    assert "⚠️" not in text


def test_skip_capabilities_prints_neither(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--skip-capabilities`` → 两条都不打，且命令照常走完（仍然成功退出）。"""
    text = _run(monkeypatch, notes=[_UNAVAILABLE_NOTE], skip_capabilities=True)

    assert "部署能力" not in text
    assert "✅ smoke_check 通过" in text


def test_unavailable_capabilities_never_fail_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺 key 是配置选择、不是未通过：这条路径不许抛（否则退出码非零）。"""
    text = _run(monkeypatch, notes=[_UNAVAILABLE_NOTE, "第二条提示"])

    assert "✅ smoke_check 通过" in text
