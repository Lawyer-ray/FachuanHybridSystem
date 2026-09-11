"""ParserFactory 测试"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.document_parsing.services.parser_factory import ParserFactory


def _fake_provider(
    *,
    name: str = "平台A",
    provider_type: str = "mineru",
    priority: int = 10,
    pk: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(name=name, provider_type=provider_type, priority=priority, pk=pk)


class TestCreateParser:
    def test_mineru_backend(self) -> None:
        parser = ParserFactory.create_parser("mineru", api_key="test-key")  # pragma: allowlist secret
        assert type(parser).__name__ == "MineruBackend"

    def test_mineru_with_timeout(self) -> None:
        parser = ParserFactory.create_parser("mineru", api_key="test-key", timeout=60)  # pragma: allowlist secret
        assert parser.timeout == 60

    def test_textin_backend(self) -> None:
        parser = ParserFactory.create_parser("textin", app_id="a", secret_code="s")  # pragma: allowlist secret
        assert type(parser).__name__ == "TextinBackend"

    def test_textin_with_timeout(self) -> None:
        parser = ParserFactory.create_parser("textin", app_id="a", secret_code="s", timeout=60)  # pragma: allowlist secret
        assert parser.timeout == 60

    def test_local_backend(self) -> None:
        parser = ParserFactory.create_parser("local")
        assert type(parser).__name__ == "LocalBackend"

    def test_unknown_backend_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="未知的后端类型"):
            ParserFactory.create_parser("foobar")


class TestAutoBackend:
    """auto 模式：按「解析平台」优先级自动选择；无平台时回退 local。"""

    def test_no_provider_falls_back_to_local(self) -> None:
        with patch(
            "apps.document_parsing.services.parser_factory.ParseProviderService.get_providers",
            return_value=[],
        ):
            parser = ParserFactory.create_parser("auto")
        assert type(parser).__name__ == "LocalBackend"

    def test_picks_highest_priority_provider(self) -> None:
        providers = [
            _fake_provider(name="低优先", provider_type="mineru", priority=20, pk=1),
            _fake_provider(name="高优先", provider_type="textin", priority=5, pk=2),
        ]
        with patch(
            "apps.document_parsing.services.parser_factory.ParseProviderService.get_providers",
            return_value=providers,
        ):
            assert ParserFactory._resolve_auto_backend() == "textin"

    def test_picks_mineru_when_only_mineru_enabled(self) -> None:
        providers = [_fake_provider(name="MinerU", provider_type="mineru", priority=10, pk=1)]
        with patch(
            "apps.document_parsing.services.parser_factory.ParseProviderService.get_providers",
            return_value=providers,
        ):
            assert ParserFactory._resolve_auto_backend() == "mineru"

    def test_auto_resolve_backend_mineru_priority(self) -> None:
        providers = [
            _fake_provider(name="T1", provider_type="textin", priority=5, pk=1),
            _fake_provider(name="M1", provider_type="mineru", priority=10, pk=2),
        ]
        with patch(
            "apps.document_parsing.services.parser_factory.ParseProviderService.get_providers",
            return_value=providers,
        ):
            assert ParserFactory._resolve_auto_backend() == "textin"
