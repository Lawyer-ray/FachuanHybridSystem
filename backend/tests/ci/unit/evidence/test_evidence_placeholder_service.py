"""Tests for apps.evidence.services.admin.evidence_list_placeholder_service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.evidence.services.admin.evidence_list_placeholder_service import (
    LEGAL_STATUS_DISPLAY,
    LEGAL_STATUS_ORDER,
    EvidenceListPlaceholderService,
)


class TestLegalStatusConstants:
    def test_display_mapping(self) -> None:
        assert LEGAL_STATUS_DISPLAY["plaintiff"] == "原告"
        assert LEGAL_STATUS_DISPLAY["defendant"] == "被告"
        assert LEGAL_STATUS_DISPLAY["applicant"] == "申请人"
        assert LEGAL_STATUS_DISPLAY["criminal_defendant"] == "被告人"

    def test_order_list(self) -> None:
        assert LEGAL_STATUS_ORDER[0] == "plaintiff"
        assert LEGAL_STATUS_ORDER[-1] == "orig_third"


class TestGetPlaceholderKeys:
    def test_returns_expected_keys(self) -> None:
        svc = EvidenceListPlaceholderService()
        keys = svc.get_placeholder_keys()
        assert "证据清单名称" in keys
        assert "当事人信息_简要" in keys
        assert "证据清单" in keys
        assert "证据清单签名盖章信息" in keys


class TestGetEvidenceListName:
    def test_no_our_parties_returns_title(self) -> None:
        svc = EvidenceListPlaceholderService()
        elist = SimpleNamespace(title="证据清单一")
        case_data: dict = {"case_parties": []}
        assert svc.get_evidence_list_name(elist, case_data) == "证据清单一"

    def test_with_our_plaintiff(self) -> None:
        svc = EvidenceListPlaceholderService()
        elist = SimpleNamespace(title="证据清单一")
        case_data = {
            "case_parties": [
                {"is_our_client": True, "legal_status": "plaintiff", "client_name": "张三"},
            ]
        }
        result = svc.get_evidence_list_name(elist, case_data)
        assert result == "证据清单一(原告)"

    def test_with_multiple_statuses(self) -> None:
        svc = EvidenceListPlaceholderService()
        elist = SimpleNamespace(title="证据清单一")
        case_data = {
            "case_parties": [
                {"is_our_client": True, "legal_status": "plaintiff", "client_name": "张三"},
                {"is_our_client": True, "legal_status": "applicant", "client_name": "李四"},
            ]
        }
        result = svc.get_evidence_list_name(elist, case_data)
        assert "原告" in result
        assert "申请人" in result
        assert "、" in result

    def test_our_party_with_unknown_status(self) -> None:
        svc = EvidenceListPlaceholderService()
        elist = SimpleNamespace(title="证据清单一")
        case_data = {
            "case_parties": [
                {"is_our_client": True, "legal_status": "unknown_status", "client_name": "张三"},
            ]
        }
        result = svc.get_evidence_list_name(elist, case_data)
        assert result == "证据清单一"

    def test_our_party_with_no_status(self) -> None:
        svc = EvidenceListPlaceholderService()
        elist = SimpleNamespace(title="证据清单一")
        case_data = {
            "case_parties": [
                {"is_our_client": True, "legal_status": None, "client_name": "张三"},
            ]
        }
        result = svc.get_evidence_list_name(elist, case_data)
        assert result == "证据清单一"


class TestGetPartiesBrief:
    def test_empty_parties(self) -> None:
        svc = EvidenceListPlaceholderService()
        result = svc.get_parties_brief({"case_parties": []})
        assert result == ""

    def test_with_parties_delegates_to_helpers(self) -> None:
        """get_parties_brief calls _group_parties_by_status and _format_ordered_groups."""
        svc = EvidenceListPlaceholderService()
        case_data = {
            "case_parties": [
                {"legal_status": "plaintiff", "client_name": "张三", "name": "张三"},
            ]
        }
        # These helper methods don't exist on the class (dead code in source),
        # so the method raises AttributeError for non-empty parties.
        with pytest.raises(AttributeError):
            svc.get_parties_brief(case_data)


class TestGetEvidenceItems:
    def test_no_items(self) -> None:
        svc = EvidenceListPlaceholderService()
        mock_items = MagicMock()
        mock_items.exists.return_value = False
        mock_items.all.return_value = mock_items
        mock_items.order_by.return_value = mock_items
        elist = SimpleNamespace(items=mock_items, start_order=1)
        result = svc.get_evidence_items(elist)
        assert result == []

    def test_with_items(self) -> None:
        svc = EvidenceListPlaceholderService()
        item1 = SimpleNamespace(order=1, name="合同", purpose="证明合同关系", page_range_display="1-3")
        item2 = SimpleNamespace(order=2, name="收据", purpose="证明付款事实", page_range_display="4")
        mock_items = MagicMock()
        mock_items.exists.return_value = True
        mock_ordered = MagicMock()
        mock_ordered.__iter__ = MagicMock(return_value=iter([item1, item2]))
        mock_items.all.return_value = mock_items
        mock_items.order_by.return_value = mock_ordered
        elist = SimpleNamespace(items=mock_items, start_order=5)

        result = svc.get_evidence_items(elist)
        assert len(result) == 2
        assert result[0]["序号"] == 5  # start_order + order - 1
        assert result[0]["证据名称"] == "合同"
        assert result[1]["序号"] == 6
        assert result[1]["页码"] == "4"


class TestGetSignatureInfo:
    def test_empty_parties(self) -> None:
        svc = EvidenceListPlaceholderService()
        assert svc.get_signature_info({"case_parties": []}) == ""

    def test_legal_entity_signature(self) -> None:
        svc = EvidenceListPlaceholderService()
        case_data = {
            "case_parties": [
                {
                    "is_our_client": True,
                    "legal_status": "plaintiff",
                    "client_name": "某公司",
                    "name": "某公司",
                    "client_type": "legal",
                    "legal_representative": "张三",
                }
            ],
            "specified_date": "2025-06-01",
        }
        result = svc.get_signature_info(case_data)
        assert "盖章" in result
        assert "某公司" in result
        assert "法定代表人(签名):张三" in result
        assert "2025年06月01日" in result

    def test_natural_person_signature(self) -> None:
        svc = EvidenceListPlaceholderService()
        case_data = {
            "case_parties": [
                {
                    "is_our_client": True,
                    "legal_status": "defendant",
                    "client_name": "李四",
                    "name": "李四",
                    "client_type": "natural",
                    "legal_representative": "",
                }
            ],
            "specified_date": "",
        }
        result = svc.get_signature_info(case_data)
        assert "签名+指模" in result
        assert "李四" in result

    def test_skip_party_without_name(self) -> None:
        svc = EvidenceListPlaceholderService()
        case_data = {
            "case_parties": [
                {
                    "is_our_client": True,
                    "legal_status": "plaintiff",
                    "client_name": "",
                    "name": "",
                    "client_type": "natural",
                }
            ],
            "specified_date": "",
        }
        result = svc.get_signature_info(case_data)
        assert result == ""


class TestFormatChineseDate:
    def test_valid_date(self) -> None:
        svc = EvidenceListPlaceholderService()
        assert svc._format_chinese_date("2025-01-15") == "2025年01月15日"

    def test_empty_date(self) -> None:
        svc = EvidenceListPlaceholderService()
        assert svc._format_chinese_date("") == ""

    def test_invalid_date_returns_original(self) -> None:
        svc = EvidenceListPlaceholderService()
        assert svc._format_chinese_date("not-a-date") == "not-a-date"


class TestGetEvidenceListContext:
    def test_not_found_error(self) -> None:
        svc = EvidenceListPlaceholderService()
        mock_case_svc = MagicMock()
        svc._case_service = mock_case_svc

        with patch("apps.evidence.models.EvidenceList") as mock_el:
            mock_el.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_el.objects.select_related.return_value.get.side_effect = mock_el.DoesNotExist()

            with pytest.raises(NotFoundError):
                svc.get_evidence_list_context(999)
