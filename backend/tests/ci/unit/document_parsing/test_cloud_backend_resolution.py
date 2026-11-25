"""云端平台解析：auto（容灾顺序）vs 锁定（不允许降级）。

这两者的差别不在"优先谁"，而在"失败怎么办"，所以本文件重点锁住：
auto 返回**有序多值**、锁定只返回**单值**、未配置时返回空表。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.document_parsing.services import parser_factory
from apps.document_parsing.services.parser_factory import resolve_cloud_backends


class _Provider:
    def __init__(self, provider_type: str, priority: int, pk: int) -> None:
        self.provider_type = provider_type
        self.priority = priority
        self.pk = pk
        self.name = provider_type


@pytest.fixture
def providers(monkeypatch: pytest.MonkeyPatch) -> Any:
    """装一组「解析平台」行，并把 DeepSeek 钉成**未配置**。

    DeepSeek 的可用性看 SystemConfig 而不是 provider 行，而 SystemConfig 有共享缓存
    （开发库配了 Key 就会漏进测试库的这次运行）。本文件测的是「provider 链」，
    所以必须把它钉死；DeepSeek 自己的口径在 `test_deepseek_backend.py` 里测。
    """

    def _install(rows: list[_Provider]) -> None:
        monkeypatch.setattr(parser_factory.ParseProviderService, "get_providers", classmethod(lambda cls: rows))
        monkeypatch.setattr(parser_factory, "_deepseek_configured", lambda: False)

    return _install


class TestAuto:
    def test_按优先级给出有序候选_可容灾(self, providers: Any) -> None:
        providers([_Provider("mineru", 5, 1), _Provider("textin", 10, 2)])
        assert resolve_cloud_backends("auto") == ["mineru", "textin"]

    def test_优先级对调后顺序跟着变(self, providers: Any) -> None:
        providers([_Provider("mineru", 20, 1), _Provider("textin", 5, 2)])
        assert resolve_cloud_backends("auto") == ["textin", "mineru"]

    def test_None_视同_auto(self, providers: Any) -> None:
        providers([_Provider("mineru", 5, 1), _Provider("textin", 10, 2)])
        assert resolve_cloud_backends(None) == ["mineru", "textin"]

    def test_同类型多平台只留最高优先级那个(self, providers: Any) -> None:
        providers([_Provider("mineru", 5, 1), _Provider("mineru", 1, 2), _Provider("textin", 10, 3)])
        # 去重后 mineru 只出现一次，且排在前面（pk=2 优先级 1 更靠前）
        assert resolve_cloud_backends("auto") == ["mineru", "textin"]


class TestLocked:
    def test_锁定MinerU只返回它(self, providers: Any) -> None:
        providers([_Provider("mineru", 5, 1), _Provider("textin", 10, 2)])
        # 关键：不含 textin —— 锁定意味着失败不降级
        assert resolve_cloud_backends("mineru") == ["mineru"]

    def test_锁定Textin只返回它(self, providers: Any) -> None:
        providers([_Provider("mineru", 5, 1), _Provider("textin", 10, 2)])
        assert resolve_cloud_backends("textin") == ["textin"]

    def test_锁定的平台未启用时返回空表(self, providers: Any) -> None:
        providers([_Provider("mineru", 5, 1)])
        # 不静默换成 mineru：让上层明确报"该平台不可用"，保持可预期
        assert resolve_cloud_backends("textin") == []


class TestEdgeCases:
    def test_无任何配置返回空表(self, providers: Any) -> None:
        providers([])
        assert resolve_cloud_backends("auto") == []

    def test_未知值按auto处理(self, providers: Any) -> None:
        # 传脏值不该让整次解析失败
        providers([_Provider("mineru", 5, 1), _Provider("textin", 10, 2)])
        assert resolve_cloud_backends("bogus") == ["mineru", "textin"]

    def test_大小写不敏感(self, providers: Any) -> None:
        providers([_Provider("mineru", 5, 1), _Provider("textin", 10, 2)])
        assert resolve_cloud_backends("MINERU") == ["mineru"]


class TestDeepSeekAvailability:
    """DeepSeek 是唯一「凭证在 SystemConfig、没有 provider 行」的平台，可用性单独一条判据。"""

    def test_Key未配置时auto链里没有它(self, providers: Any) -> None:
        providers([_Provider("mineru", 5, 1)])
        assert resolve_cloud_backends("auto") == ["mineru"]

    def test_Key已配置时追加在最后(self, providers: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        providers([_Provider("mineru", 5, 1), _Provider("textin", 10, 2)])
        monkeypatch.setattr(parser_factory, "_deepseek_configured", lambda: True)
        # 是**兜底**不是首选：想让它当首选得显式锁定
        assert resolve_cloud_backends("auto") == ["mineru", "textin", "deepseek"]

    def test_只有Key没有任何provider时auto只给deepseek(self, providers: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        providers([])
        monkeypatch.setattr(parser_factory, "_deepseek_configured", lambda: True)
        assert resolve_cloud_backends("auto") == ["deepseek"]

    def test_一个平台都没有时返回空表(self, providers: Any) -> None:
        providers([])
        assert resolve_cloud_backends("auto") == []
