"""``deployment_capabilities``（部署能力自检）的判据单测。

本模块只做「把已有判据翻成一句人话」，所以用例全部打在它的**两个上游**上：
``disagreement_judge.gate_state`` 与 ``parser_factory.resolve_cloud_backends``。
不碰数据库、不读 SystemConfig、也不在这里重测 gate 的状态机——那样等于把判据复制一遍。

重点锁住两件容易退化的事：

1. **两个「关着」不许混成一句**：``gate_off``（没开开关）与 ``missing_key``（开了没填 Key）
   让运维去改的是两个不同配置项，所以同一条 note 里不许同时出现两者。
2. **自检不许崩**：读配置 / 读 provider 抛异常时必须降级成「不可用 + 一条提示」，
   否则 ``smoke_check`` 会因为一个只读检查而假红，从此没人看它。
"""

from __future__ import annotations

import pytest
from django.db import DatabaseError

from apps.document_parsing.services import parser_factory
from apps.pdf_splitting.services import capabilities
from apps.pdf_splitting.services.split import disagreement_judge

#: 三个云端取字平台（与 ``parser_factory.CLOUD_BACKEND_CHOICES`` 同一组名字）。
_ALL_ENGINES = ("mineru", "textin", "deepseek")


def _stub_gate(monkeypatch: pytest.MonkeyPatch, *, enabled: bool, reason: str) -> None:
    """钉住判定的部署级门禁（原因码见 ``disagreement_judge.GATE_*``）。"""
    monkeypatch.setattr(disagreement_judge, "gate_state", lambda: (enabled, reason))


def _stub_backends(monkeypatch: pytest.MonkeyPatch, available: list[str]) -> None:
    """钉住「当前可用的云端平台」，即 ``resolve_cloud_backends`` 的返回值。"""
    monkeypatch.setattr(parser_factory, "resolve_cloud_backends", lambda cloud_backend=None: list(available))


def _stub_backends_raising(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    """让「读平台配置」抛指定异常（真实形态是 provider 表读不到）。"""

    def _boom(cloud_backend: str | None = None) -> list[str]:
        raise exc

    monkeypatch.setattr(parser_factory, "resolve_cloud_backends", _boom)


def test_all_available_has_no_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    """全可用 → ``notes`` 空列表（调用方据此打那一行 ✅）。"""
    _stub_gate(monkeypatch, enabled=True, reason=disagreement_judge.GATE_ENABLED)
    _stub_backends(monkeypatch, list(_ALL_ENGINES))

    result = capabilities.deployment_capabilities()

    assert result["notes"] == []
    assert result["engines"] == {"mineru": True, "textin": True, "deepseek": True}
    assert result["judge"] == {"enabled": True, "reason": disagreement_judge.GATE_ENABLED}


def test_gate_off_points_at_the_switch_not_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """总闸关着 → 只提 ``OCR_JUDGE_ENABLED``；此时提 Key 等于把人引到错的那个配置项。"""
    _stub_gate(monkeypatch, enabled=False, reason=disagreement_judge.GATE_OFF)
    _stub_backends(monkeypatch, list(_ALL_ENGINES))

    result = capabilities.deployment_capabilities()
    notes = result["notes"]

    assert result["judge"] == {"enabled": False, "reason": disagreement_judge.GATE_OFF}
    assert any("OCR_JUDGE_ENABLED=0" in note for note in notes)
    assert not any("OCR_JUDGE_API_KEY" in note for note in notes), (
        "gate_off 与 missing_key 让运维改的是两个不同配置项，note 里不许混"
    )


def test_missing_key_points_at_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """开了却缺 Key → 只提 ``OCR_JUDGE_API_KEY``，且原因码原样透出。"""
    _stub_gate(monkeypatch, enabled=False, reason=disagreement_judge.GATE_MISSING_KEY)
    _stub_backends(monkeypatch, list(_ALL_ENGINES))

    result = capabilities.deployment_capabilities()
    notes = result["notes"]

    assert result["judge"] == {"enabled": False, "reason": disagreement_judge.GATE_MISSING_KEY}
    assert any("OCR_JUDGE_API_KEY" in note for note in notes)
    assert not any("OCR_JUDGE_ENABLED=0" in note for note in notes)


def test_no_cloud_engine_says_local_ocr_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """三引擎全不可用 → 说清「现在只剩本地 OCR」，而不是留一张全 False 的表让人自己猜。"""
    _stub_gate(monkeypatch, enabled=True, reason=disagreement_judge.GATE_ENABLED)
    _stub_backends(monkeypatch, [])

    result = capabilities.deployment_capabilities()

    assert result["engines"] == {"mineru": False, "textin": False, "deepseek": False}
    assert any("只能走本地 OCR" in note for note in result["notes"])


def test_deepseek_only_missing_warns_about_locking(monkeypatch: pytest.MonkeyPatch) -> None:
    """只有一个平台缺 Key → 只说「别去锁定它」，不能说成「全部不可用」。"""
    _stub_gate(monkeypatch, enabled=True, reason=disagreement_judge.GATE_ENABLED)
    _stub_backends(monkeypatch, ["mineru"])

    result = capabilities.deployment_capabilities()
    notes = result["notes"]

    assert result["engines"] == {"mineru": True, "textin": False, "deepseek": False}
    assert any("锁定它会直接失败" in note for note in notes)
    assert not any("全部不可用" in note for note in notes)


def test_provider_read_failure_degrades_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """读 provider 抛异常（provider 表读不到）→ 不抛、engines 全 False，并留一条可定位的提示。"""
    _stub_gate(monkeypatch, enabled=True, reason=disagreement_judge.GATE_ENABLED)
    _stub_backends_raising(monkeypatch, DatabaseError("解析平台表读不到"))

    result = capabilities.deployment_capabilities()

    assert result["engines"] == {"mineru": False, "textin": False, "deepseek": False}
    assert result["notes"], "读不到 provider 时必须留提示，否则又回到「静默空转」"
    assert any("读取失败" in note for note in result["notes"])


def test_judge_config_read_failure_uses_its_own_reason_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """读系统配置抛异常 → 不抛、judge 记不可用，原因码是自检自己的 ``unreadable``。

    刻意不借用 ``gate_off``：那会让运维以为「只是没开开关」，而实际是配置读不出来。
    """

    def _boom() -> tuple[bool, str]:
        raise DatabaseError("系统配置表读不到")

    monkeypatch.setattr(disagreement_judge, "gate_state", _boom)
    _stub_backends(monkeypatch, list(_ALL_ENGINES))

    result = capabilities.deployment_capabilities()

    assert result["judge"] == {"enabled": False, "reason": capabilities.JUDGE_REASON_UNREADABLE}
    assert result["engines"] == {"mineru": True, "textin": True, "deepseek": True}
    assert any("读取失败" in note for note in result["notes"])
