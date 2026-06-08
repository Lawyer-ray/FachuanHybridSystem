"""合同显示服务与模板缓存单元测试。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.contract.query.display_service import ContractDisplayService
from apps.contracts.services.contract.query.template_cache import ContractTemplateCache


# ── ContractDisplayService ─────────────────────────────────────────────────

class TestContractDisplayService:

    def _service(self, doc_service=None, cache=None) -> ContractDisplayService:
        return ContractDisplayService(
            document_service=doc_service or MagicMock(),
            template_cache=cache or ContractTemplateCache(),
        )

    def _contract(self, case_type="civil", pk=1) -> SimpleNamespace:
        return SimpleNamespace(case_type=case_type, id=pk, pk=pk)

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_get_matched_document_template_from_cache(self, mock_cache_cls) -> None:
        """从缓存获取文书模板。"""
        mock_cache = MagicMock()
        mock_cache.get_document_templates.return_value = [
            {"name": "起诉状", "type_display": "一审"}
        ]
        svc = self._service(cache=mock_cache)
        result = svc.get_matched_document_template(self._contract())
        assert "起诉状" in result

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_get_matched_document_template_cache_miss(self, mock_cache_cls) -> None:
        """缓存未命中从数据库查询。"""
        mock_cache = MagicMock()
        mock_cache.get_document_templates.return_value = None
        mock_doc_service = MagicMock()
        mock_doc_service.find_matching_contract_templates.return_value = [
            {"name": "答辩状", "type_display": ""}
        ]
        svc = self._service(doc_service=mock_doc_service, cache=mock_cache)
        result = svc.get_matched_document_template(self._contract())
        assert "答辩状" in result
        mock_cache.set_document_templates.assert_called_once()

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_get_matched_document_template_empty(self, mock_cache_cls) -> None:
        """无匹配模板返回"无匹配模板"。"""
        mock_cache = MagicMock()
        mock_cache.get_document_templates.return_value = []
        svc = self._service(cache=mock_cache)
        result = svc.get_matched_document_template(self._contract())
        assert result == "无匹配模板"

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_get_matched_document_template_exception(self, mock_cache_cls) -> None:
        """异常时返回"查询失败"。"""
        mock_cache = MagicMock()
        mock_cache.get_document_templates.side_effect = Exception("DB error")
        svc = self._service(cache=mock_cache)
        result = svc.get_matched_document_template(self._contract())
        assert result == "查询失败"

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_get_matched_folder_templates(self, mock_cache_cls) -> None:
        """获取文件夹模板。"""
        mock_cache = MagicMock()
        mock_cache.get_folder_templates.return_value = [
            {"name": "诉讼材料"},
        ]
        svc = self._service(cache=mock_cache)
        result = svc.get_matched_folder_templates(self._contract())
        assert "诉讼材料" in result

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_get_matched_folder_templates_empty(self, mock_cache_cls) -> None:
        """无文件夹模板返回"无匹配模板"。"""
        mock_cache = MagicMock()
        mock_cache.get_folder_templates.return_value = []
        svc = self._service(cache=mock_cache)
        result = svc.get_matched_folder_templates(self._contract())
        assert result == "无匹配模板"

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_has_matched_templates_both_present(self, mock_cache_cls) -> None:
        """同时有文书和文件夹模板返回 True。"""
        mock_cache = MagicMock()
        mock_cache.get_template_check.return_value = {"has_folder": True, "has_document": True}
        svc = self._service(cache=mock_cache)
        assert svc.has_matched_templates(self._contract()) is True

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_has_matched_templates_missing_folder(self, mock_cache_cls) -> None:
        """缺少文件夹模板返回 False。"""
        mock_cache = MagicMock()
        mock_cache.get_template_check.return_value = {"has_folder": False, "has_document": True}
        svc = self._service(cache=mock_cache)
        assert svc.has_matched_templates(self._contract()) is False

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_has_matched_templates_missing_document(self, mock_cache_cls) -> None:
        """缺少文书模板返回 False。"""
        mock_cache = MagicMock()
        mock_cache.get_template_check.return_value = {"has_folder": True, "has_document": False}
        svc = self._service(cache=mock_cache)
        assert svc.has_matched_templates(self._contract()) is False

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_has_matched_templates_exception(self, mock_cache_cls) -> None:
        """异常时返回 False。"""
        mock_cache = MagicMock()
        mock_cache.get_template_check.side_effect = Exception("error")
        svc = self._service(cache=mock_cache)
        assert svc.has_matched_templates(self._contract()) is False

    @patch("apps.contracts.services.contract.query.display_service.ContractTemplateCache")
    def test_batch_get_template_info_empty(self, mock_cache_cls) -> None:
        """空列表返回空字典。"""
        svc = self._service()
        assert svc.batch_get_template_info([]) == {}


# ── ContractTemplateCache ──────────────────────────────────────────────────

class TestContractTemplateCache:

    def test_get_cache_key_format(self) -> None:
        """缓存键格式正确。"""
        cache = ContractTemplateCache()
        key = cache._get_cache_key("civil", "document_templates", 1)
        assert key == "contract_template:civil:document_templates:1"

    @patch("apps.contracts.services.contract.query.template_cache.cache")
    def test_get_document_templates_returns_cached(self, mock_cache) -> None:
        """从缓存获取文书模板。"""
        # 第一次调用是 _get_cache_version (返回版本号)，第二次是实际缓存 get
        mock_cache.get.side_effect = [1, [{"name": "起诉状"}]]
        svc = ContractTemplateCache()
        result = svc.get_document_templates("civil")
        assert result == [{"name": "起诉状"}]

    @patch("apps.contracts.services.contract.query.template_cache.cache")
    def test_get_document_templates_miss(self, mock_cache) -> None:
        """缓存未命中返回 None。"""
        mock_cache.get.side_effect = [1, None]
        svc = ContractTemplateCache()
        result = svc.get_document_templates("civil")
        assert result is None

    @patch("apps.contracts.services.contract.query.template_cache.cache")
    def test_set_document_templates(self, mock_cache) -> None:
        """设置文书模板缓存。"""
        mock_cache.get.return_value = 1
        svc = ContractTemplateCache()
        templates = [{"name": "起诉状"}]
        svc.set_document_templates("civil", templates)
        mock_cache.set.assert_called_once()

    @patch("apps.contracts.services.contract.query.template_cache.cache")
    def test_clear_cache_for_case_type(self, mock_cache) -> None:
        """清除特定案件类型的缓存。"""
        mock_cache.get.return_value = 1
        svc = ContractTemplateCache()
        svc.clear_cache_for_case_type("civil")
        mock_cache.delete_many.assert_called_once()
