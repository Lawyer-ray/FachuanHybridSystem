"""client_import_api._enrich_enterprise_data 单元测试。

mock ClientEnterprisePrefillService（企业数据查询），断言：
- 无搜索结果 → None
- 精确匹配优先、无精确匹配时回退第一个候选
- 无 company_id → None；查询异常 → None（预填失败不影响主流程）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from apps.oa_filing.api.client_import_api import _enrich_enterprise_data


def _service_mock(search_result: dict | Exception, prefill_result: dict | None = None) -> MagicMock:
    service = MagicMock()
    if isinstance(search_result, Exception):
        service.search_companies.side_effect = search_result
    else:
        service.search_companies.return_value = search_result
    if prefill_result is not None:
        service.build_prefill.return_value = prefill_result
    return service


class TestEnrichEnterpriseData:
    def test_no_items_returns_none(self):
        service = _service_mock({"items": []})
        with patch(
            "apps.client.services.client_enterprise_prefill_service.ClientEnterprisePrefillService",
            MagicMock(return_value=service),
        ):
            assert _enrich_enterprise_data("不存在公司") is None
        service.search_companies.assert_called_once_with(keyword="不存在公司", limit=5)

    def test_exact_match_wins(self):
        service = _service_mock(
            {
                "items": [
                    {"company_name": "甲公司", "company_id": "id-a"},
                    {"company_name": "目标公司", "company_id": "id-b"},
                ]
            },
            prefill_result={"prefill": {"name": "目标公司", "id_number": "USCC-B", "phone": "021-1"}},
        )
        with patch(
            "apps.client.services.client_enterprise_prefill_service.ClientEnterprisePrefillService",
            MagicMock(return_value=service),
        ):
            result = _enrich_enterprise_data("目标公司")
        assert result == {"name": "目标公司", "id_number": "USCC-B", "phone": "021-1"}
        service.build_prefill.assert_called_once_with(company_id="id-b")

    def test_no_exact_match_falls_back_to_first(self):
        service = _service_mock(
            {"items": [{"company_name": "近似公司", "company_id": "id-first"}]},
            prefill_result={"prefill": {"name": "近似公司"}},
        )
        with patch(
            "apps.client.services.client_enterprise_prefill_service.ClientEnterprisePrefillService",
            MagicMock(return_value=service),
        ):
            result = _enrich_enterprise_data("完全不同")
        assert result == {"name": "近似公司"}
        service.build_prefill.assert_called_once_with(company_id="id-first")

    def test_matched_item_without_company_id_returns_none(self):
        service = _service_mock({"items": [{"company_name": "甲公司"}]})
        with patch(
            "apps.client.services.client_enterprise_prefill_service.ClientEnterprisePrefillService",
            MagicMock(return_value=service),
        ):
            assert _enrich_enterprise_data("甲公司") is None
        service.build_prefill.assert_not_called()

    def test_search_failure_returns_none(self):
        service = _service_mock(RuntimeError("企业数据接口不可用"))
        with patch(
            "apps.client.services.client_enterprise_prefill_service.ClientEnterprisePrefillService",
            MagicMock(return_value=service),
        ):
            assert _enrich_enterprise_data("任意公司") is None
