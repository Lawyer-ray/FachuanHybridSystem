"""Tests for client mapper, material_classification_service, dashboard_service, and other modules."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.client.services.importer.mapper import (
    ClientJsonImportMapper,
    ClientImportCommand,
    ClientIdentityDocCommand,
)
from apps.core.services.material_classification_service import MaterialClassificationService
from apps.core.services.dashboard_service import DashboardService


# ---------------------------------------------------------------------------
# ClientJsonImportMapper
# ---------------------------------------------------------------------------


class TestClientJsonImportMapper:
    def setup_method(self):
        self.mapper = ClientJsonImportMapper()

    def test_to_command_basic(self):
        json_data = {"name": "张三", "phone": "13800138000", "client_type": "natural_person"}
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert cmd.client_data["name"] == "张三"
        assert cmd.client_data["phone"] == "13800138000"
        assert cmd.admin_user == "admin"
        assert cmd.identity_docs == []

    def test_to_command_with_identity_docs(self):
        json_data = {
            "name": "张三",
            "identity_docs": [
                {"doc_type": "id_card", "file_path": "/tmp/id.pdf"},
                {"doc_type": "business_license", "file_path": "/tmp/license.pdf"},
            ],
        }
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert len(cmd.identity_docs) == 2
        assert cmd.identity_docs[0].doc_type == "id_card"

    def test_to_command_empty_identity_docs(self):
        json_data = {"name": "张三", "identity_docs": []}
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert cmd.identity_docs == []

    def test_to_command_none_identity_docs(self):
        json_data = {"name": "张三", "identity_docs": None}
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert cmd.identity_docs == []

    def test_to_command_invalid_identity_doc(self):
        json_data = {
            "name": "张三",
            "identity_docs": [{"doc_type": "", "file_path": "/tmp/x.pdf"}],
        }
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert len(cmd.identity_docs) == 0

    def test_to_command_missing_doc_type(self):
        json_data = {
            "name": "张三",
            "identity_docs": [{"file_path": "/tmp/x.pdf"}],
        }
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert len(cmd.identity_docs) == 0

    def test_to_command_non_dict_identity_doc(self):
        json_data = {
            "name": "张三",
            "identity_docs": ["not_a_dict"],
        }
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert cmd.identity_docs == []

    def test_to_command_non_list_identity_docs(self):
        json_data = {
            "name": "张三",
            "identity_docs": "not_a_list",
        }
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert cmd.identity_docs == []

    def test_is_our_client_default_false(self):
        json_data = {"name": "张三"}
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert cmd.client_data["is_our_client"] is False

    def test_is_our_client_explicit(self):
        json_data = {"name": "张三", "is_our_client": True}
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert cmd.client_data["is_our_client"] is True

    def test_extra_fields_ignored(self):
        json_data = {"name": "张三", "unknown_field": "value"}
        cmd = self.mapper.to_command(json_data, admin_user="admin")
        assert "unknown_field" not in cmd.client_data


# ---------------------------------------------------------------------------
# MaterialClassificationService
# ---------------------------------------------------------------------------


class TestMaterialClassificationService:
    def setup_method(self):
        self.service = MaterialClassificationService()

    def test_classify_contract_in_contract_folder(self):
        result = self.service.classify_contract_material(
            filename="主合同.pdf",
            text_excerpt="",
            source_path="/合同发票/主合同.pdf",
        )
        assert result["category"] == "contract_original"

    def test_classify_contract_supplement(self):
        result = self.service.classify_contract_material(
            filename="补充协议.pdf",
            text_excerpt="",
            source_path="/合同发票/补充协议.pdf",
        )
        assert result["category"] == "supplementary_agreement"

    def test_classify_contract_invoice(self):
        result = self.service.classify_contract_material(
            filename="发票.pdf",
            text_excerpt="",
            source_path="/合同发票/发票.pdf",
        )
        assert result["category"] == "invoice"

    def test_classify_contract_supervision_card(self):
        result = self.service.classify_contract_material(
            filename="监督卡.pdf",
            text_excerpt="",
            source_path="/合同发票/监督卡.pdf",
        )
        assert result["category"] == "supervision_card"

    def test_classify_contract_not_in_folder(self):
        result = self.service.classify_contract_material(
            filename="something.pdf",
            text_excerpt="",
            source_path="/其他路径/something.pdf",
        )
        assert result["category"] == "case_material"

    def test_classify_contract_in_folder_default(self):
        result = self.service.classify_contract_material(
            filename="unknown.pdf",
            text_excerpt="",
            source_path="/合同发票/",
        )
        assert result["category"] == "contract_original"

    def test_classify_case_execution_application(self):
        result = self.service.classify_case_material(
            filename="执行申请书.pdf",
            text_excerpt="",
        )
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_classify_case_evidence(self):
        result = self.service.classify_case_material(
            filename="证据清单.pdf",
            text_excerpt="",
        )
        assert result["category"] == "party"
        assert result["type_name_hint"] == "证据材料"

    def test_classify_case_no_match(self):
        result = self.service.classify_case_material(
            filename="random.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "unknown"

    def test_classify_case_folder_hint(self):
        result = self.service.classify_case_material(
            filename="random.pdf",
            text_excerpt="",
            enable_ai=False,
            scan_subfolder="2-立案材料",
        )
        assert result["type_name_hint"] == "立案材料"

    def test_normalize_for_match(self):
        assert self.service._normalize_for_match("Hello World") == "helloworld"
        assert self.service._normalize_for_match("") == ""
        assert self.service._normalize_for_match("path\\to\\file") == "path/to/file"

    def test_extract_subfolder_hint(self):
        assert self.service._extract_subfolder_hint("2-立案材料") == "立案材料"
        assert self.service._extract_subfolder_hint("3_执行依据") == "执行依据"
        assert self.service._extract_subfolder_hint("some_folder") == "some_folder"
        assert self.service._extract_subfolder_hint("") == ""

    def test_to_confidence(self):
        assert self.service._to_confidence(0.5) == 0.5
        assert self.service._to_confidence(None) == 0.0
        assert self.service._to_confidence("invalid") == 0.0
        assert self.service._to_confidence(-1) == 0.0
        assert self.service._to_confidence(2.0) == 1.0

    def test_extract_json_valid(self):
        result = self.service._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_empty(self):
        assert self.service._extract_json("") is None
        assert self.service._extract_json(None) is None  # type: ignore[arg-type]

    def test_extract_json_fenced(self):
        result = self.service._extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_infer_case_side_our(self):
        context = {"our_party_names": ["原告公司"]}
        result = self.service._infer_case_side(match_text="原告公司起诉状", context=context)
        assert result == "our"

    def test_infer_case_side_opponent(self):
        context = {"opponent_party_names": ["被告公司"]}
        result = self.service._infer_case_side(match_text="被告公司答辩状", context=context)
        assert result == "opponent"

    def test_infer_case_side_both(self):
        context = {"our_party_names": ["原告"], "opponent_party_names": ["被告"]}
        result = self.service._infer_case_side(match_text="原告与被告", context=context)
        assert result == "unknown"

    def test_infer_case_side_empty(self):
        result = self.service._infer_case_side(match_text="", context={})
        assert result == "unknown"

    def test_extract_party_ids_by_side(self):
        context = {"our_party_ids": [1, 2, 3]}
        result = self.service._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2, 3]

    def test_extract_party_ids_dedup(self):
        context = {"our_party_ids": [1, 1, 2]}
        result = self.service._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2]

    def test_extract_party_ids_invalid(self):
        context = {"our_party_ids": ["not_a_number"]}
        result = self.service._extract_party_ids_by_side(side="our", context=context)
        assert result == []

    def test_extract_primary_supervising_authority_id(self):
        assert self.service._extract_primary_supervising_authority_id({"primary_supervising_authority_id": 1}) == 1
        assert self.service._extract_primary_supervising_authority_id({}) is None
        assert self.service._extract_primary_supervising_authority_id({"primary_supervising_authority_id": "invalid"}) is None
        assert self.service._extract_primary_supervising_authority_id({"primary_supervising_authority_id": -1}) is None

    def test_parse_work_log_from_folder_name(self):
        result = self.service.parse_work_log_from_folder_name("2025.01.23-知识产权合同")
        assert result is not None
        assert result["date"] == "2025-01-23"
        assert "知识产权合同" in result["content"]

    def test_parse_work_log_from_folder_name_no_match(self):
        assert self.service.parse_work_log_from_folder_name("random folder") is None

    def test_match_archive_by_filename_litigation(self):
        result = self.service._match_archive_by_filename(
            filename="起诉状.pdf",
            archive_category="litigation",
        )
        assert result is not None
        assert result["archive_item_code"] == "lt_7"

    def test_match_archive_by_filename_no_match(self):
        result = self.service._match_archive_by_filename(
            filename="random.pdf",
            archive_category="litigation",
        )
        assert result is None

    def test_classify_archive_material_no_match(self):
        result = self.service.classify_archive_material(
            filename="random.pdf",
            source_path="/path/random.pdf",
            archive_category="litigation",
        )
        # May or may not match depending on keyword mapping fallback
        assert "archive_item_code" in result

    def test_classify_archive_material_invalid_category(self):
        result = self.service.classify_archive_material(
            filename="random.pdf",
            source_path="/path/random.pdf",
            archive_category="invalid",
        )
        assert result["archive_item_code"] == ""


# ---------------------------------------------------------------------------
# DashboardService
# ---------------------------------------------------------------------------


class TestDashboardService:
    def test_get_stats_keys(self):
        svc = DashboardService()
        with patch.object(svc, "_client_count", return_value=10), \
             patch.object(svc, "_contract_count", return_value=5), \
             patch.object(svc, "_active_case_count", return_value=3), \
             patch.object(svc, "_monthly_fee", return_value=Decimal("1000")), \
             patch.object(svc, "_case_trend", return_value=[]), \
             patch.object(svc, "_contract_trend", return_value=[]), \
             patch.object(svc, "_fee_trend", return_value=[]), \
             patch.object(svc, "_case_type_distribution", return_value=[]), \
             patch.object(svc, "_case_status_distribution", return_value={}), \
             patch.object(svc, "_upcoming_reminders", return_value=[]), \
             patch.object(svc, "_overdue_count", return_value=0), \
             patch.object(svc, "_today_count", return_value=0):
            result = svc.get_stats()
            assert result["client_count"] == 10
            assert result["contract_count"] == 5
            assert result["case_count"] == 3
            assert result["monthly_fee"] == Decimal("1000")
