"""ParserFactory 测试"""

from unittest.mock import MagicMock, patch

import pytest

from apps.document_parsing.services.parser_factory import ParserFactory


class TestCreateParser:
    def test_mineru_backend(self) -> None:
        with (
            patch("apps.document_parsing.services.backends.mineru_backend.get_sync_http_client"),
            patch("apps.document_parsing.services.backends.mineru_backend._config_service") as mock_cfg,
        ):
            mock_cfg.get_value_internal.return_value = "test-key"
            parser = ParserFactory.create_parser("mineru")
            assert type(parser).__name__ == "MineruBackend"

    def test_mineru_with_timeout(self) -> None:
        with (
            patch("apps.document_parsing.services.backends.mineru_backend.get_sync_http_client"),
            patch("apps.document_parsing.services.backends.mineru_backend._config_service") as mock_cfg,
        ):
            mock_cfg.get_value_internal.return_value = "test-key"
            parser = ParserFactory.create_parser("mineru", timeout=60)
            assert parser.timeout == 60

    def test_textin_backend(self) -> None:
        with (
            patch("apps.document_parsing.services.backends.textin_backend.xc.XParseClient"),
            patch("apps.document_parsing.services.backends.textin_backend._config_service") as mock_cfg,
        ):
            mock_cfg.get_value_internal.side_effect = ["cfg-app", "cfg-secret"]
            parser = ParserFactory.create_parser("textin")
            assert type(parser).__name__ == "TextinBackend"

    def test_textin_with_timeout(self) -> None:
        with (
            patch("apps.document_parsing.services.backends.textin_backend.xc.XParseClient"),
            patch("apps.document_parsing.services.backends.textin_backend._config_service") as mock_cfg,
        ):
            mock_cfg.get_value_internal.side_effect = ["cfg-app", "cfg-secret"]
            parser = ParserFactory.create_parser("textin", timeout=60)
            assert parser.timeout == 60

    def test_local_backend(self) -> None:
        parser = ParserFactory.create_parser("local")
        assert type(parser).__name__ == "LocalBackend"

    def test_unknown_backend_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="未知的后端类型"):
            ParserFactory.create_parser("foobar")

    def test_auto_reads_system_config(self) -> None:
        with patch("apps.document_parsing.services.parser_factory._config_service") as mock_cfg:
            mock_cfg.get_value_internal.return_value = "local"
            parser = ParserFactory.create_parser("auto")
            assert type(parser).__name__ == "LocalBackend"
            mock_cfg.get_value_internal.assert_called_once_with("DOCUMENT_PARSING_BACKEND", "mineru")

    def test_auto_defaults_to_mineru(self) -> None:
        with (
            patch("apps.document_parsing.services.backends.mineru_backend.get_sync_http_client"),
            patch("apps.document_parsing.services.parser_factory._config_service") as mock_factory_cfg,
            patch("apps.document_parsing.services.backends.mineru_backend._config_service") as mock_mineru_cfg,
        ):
            mock_factory_cfg.get_value_internal.return_value = "mineru"
            mock_mineru_cfg.get_value_internal.return_value = "test-key"
            parser = ParserFactory.create_parser("auto")
            assert type(parser).__name__ == "MineruBackend"
