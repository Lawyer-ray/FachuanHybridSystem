"""contract_review 模块 0% 覆盖率文件单元测试

覆盖文件:
- apps/contract_review/services/contract_format_service.py
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

import pytest


class TestContractFormatServiceDetermineMethod:
    """ContractFormatService._determine_method 测试"""

    def _make_service(self):
        from apps.contract_review.services.contract_format_service import ContractFormatService

        with patch("apps.contract_review.services.contract_format_service.get_poi_client") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            svc = ContractFormatService()
            return svc, mock_client

    def test_force_method_poi(self):
        svc, _ = self._make_service()
        result = svc._determine_method("poi")
        assert result == "poi"

    def test_force_method_python(self):
        svc, _ = self._make_service()
        result = svc._determine_method("python")
        assert result == "python"

    def test_force_method_auto_poi_available(self):
        svc, mock_client = self._make_service()
        mock_client.health_check.return_value = True
        result = svc._determine_method("auto")
        assert result == "poi"

    def test_force_method_auto_poi_unavailable(self):
        svc, mock_client = self._make_service()
        mock_client.health_check.return_value = False
        result = svc._determine_method("auto")
        assert result == "python"

    def test_force_method_none_poi_available(self):
        svc, mock_client = self._make_service()
        mock_client.health_check.return_value = True
        result = svc._determine_method(None)
        assert result == "poi"

    def test_force_method_none_poi_unavailable(self):
        svc, mock_client = self._make_service()
        mock_client.health_check.return_value = False
        result = svc._determine_method(None)
        assert result == "python"


class TestContractFormatServiceFormatWithPoi:
    """ContractFormatService._format_with_poi 测试"""

    def _make_service(self):
        from apps.contract_review.services.contract_format_service import ContractFormatService

        with patch("apps.contract_review.services.contract_format_service.get_poi_client") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            svc = ContractFormatService()
            return svc, mock_client

    def test_format_with_poi_success(self):
        svc, mock_client = self._make_service()
        mock_client.format_contract.return_value = b"formatted_docx"

        result_bytes, method = svc._format_with_poi(b"original", {"font": "宋体"})
        assert result_bytes == b"formatted_docx"
        assert method == "poi"

    def test_format_with_poi_exception(self):
        svc, mock_client = self._make_service()
        mock_client.format_contract.side_effect = ConnectionError("POI down")

        with pytest.raises(ConnectionError):
            svc._format_with_poi(b"original", None)


class TestContractFormatServiceFormatWithPython:
    """ContractFormatService._format_with_python 测试"""

    def _make_service(self):
        from apps.contract_review.services.contract_format_service import ContractFormatService

        with patch("apps.contract_review.services.contract_format_service.get_poi_client") as mock_get:
            mock_get.return_value = MagicMock()
            svc = ContractFormatService()
            return svc

    @patch("apps.contract_review.services.contract_format_service.ContractFormatService._format_with_python")
    def test_format_with_python_returns_tuple(self, mock_format):
        mock_format.return_value = (b"python_formatted", "python")
        svc = self._make_service()
        result_bytes, method = svc._format_with_python(b"docx_bytes", None)
        assert method == "python"


class TestContractFormatServiceFormatContract:
    """ContractFormatService.format_contract 集成路径测试"""

    def _make_service(self):
        from apps.contract_review.services.contract_format_service import ContractFormatService

        with patch("apps.contract_review.services.contract_format_service.get_poi_client") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            svc = ContractFormatService()
            return svc, mock_client

    def test_format_contract_file_not_found(self):
        svc, _ = self._make_service()
        task = SimpleNamespace(
            id=1,
            original_file="nonexistent.docx",
            contract_title="test",
        )

        with patch("apps.contract_review.services.contract_format_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/tmp/nonexistent"
            with pytest.raises(ValueError, match="原始文件不存在"):
                svc.format_contract(task)

    @patch("apps.contract_review.services.contract_format_service.ContractFormatService._format_with_poi")
    def test_format_contract_success_poi(self, mock_poi):
        svc, mock_client = self._make_service()
        mock_client.health_check.return_value = True
        mock_poi.return_value = (b"result", "poi")

        task = SimpleNamespace(
            id=1,
            original_file="contracts/test.docx",
            contract_title="TestContract",
            save=MagicMock(),
        )

        with patch("apps.contract_review.services.contract_format_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/tmp/media"
            with patch("apps.contract_review.services.contract_format_service.default_storage") as mock_storage:
                mock_storage.save.side_effect = lambda rel, f: rel
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.read_bytes", return_value=b"docx_data"):
                        with patch("pathlib.Path.write_bytes"):
                            output_path, method = svc.format_contract(task)
                            assert method == "poi"
                            task.save.assert_called_once_with(update_fields=["output_file"])
