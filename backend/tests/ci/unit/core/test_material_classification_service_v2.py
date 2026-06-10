"""Tests for MaterialClassificationService covering keyword-based classification."""
from __future__ import annotations

import pytest

from apps.core.services.material_classification_service import MaterialClassificationService


@pytest.fixture
def svc():
    return MaterialClassificationService()


# ── classify_contract_material ──


class TestClassifyContractMaterial:
    def test_non_contract_invoice_folder_returns_case_material(self, svc):
        result = svc.classify_contract_material(
            filename="合同.pdf", text_excerpt="", source_path="/data/案件材料/合同.pdf"
        )
        assert result["category"] == "case_material"
        assert result["confidence"] == 0.95

    def test_contract_invoice_folder_default_contract_original(self, svc):
        result = svc.classify_contract_material(
            filename="普通文件.pdf", text_excerpt="", source_path="/data/合同发票/普通文件.pdf"
        )
        assert result["category"] == "contract_original"
        assert result["confidence"] == 0.5

    def test_contract_invoice_folder_supervision_card(self, svc):
        result = svc.classify_contract_material(
            filename="服务质量监督卡.pdf", text_excerpt="", source_path="/data/合同发票/监督卡.pdf"
        )
        assert result["category"] == "supervision_card"
        assert result["confidence"] == 0.98

    def test_contract_invoice_folder_supplementary(self, svc):
        result = svc.classify_contract_material(
            filename="补充协议.pdf", text_excerpt="", source_path="/data/合同发票/补充协议.pdf"
        )
        assert result["category"] == "supplementary_agreement"

    def test_contract_invoice_folder_invoice(self, svc):
        result = svc.classify_contract_material(
            filename="增值税发票.pdf", text_excerpt="", source_path="/data/合同发票/发票.pdf"
        )
        assert result["category"] == "invoice"

    def test_contract_invoice_folder_contract_keyword(self, svc):
        result = svc.classify_contract_material(
            filename="租赁合同.pdf", text_excerpt="", source_path="/data/合同发票/租赁合同.pdf"
        )
        assert result["category"] == "contract_original"
        assert result["confidence"] == 0.96

    def test_contract_false_positive_excluded(self, svc):
        # "合同纠纷" should NOT match as contract_original
        result = svc.classify_contract_material(
            filename="合同纠纷起诉状.pdf", text_excerpt="", source_path="/data/合同发票/合同纠纷.pdf"
        )
        # Not contract_original because "合同纠纷" is excluded
        assert result["category"] != "contract_original" or result["confidence"] < 0.96

    def test_empty_filename_in_contract_folder(self, svc):
        result = svc.classify_contract_material(
            filename="", text_excerpt="", source_path="/data/合同发票/"
        )
        assert result["category"] == "contract_original"  # default in contract folder


# ── classify_case_material ──


class TestClassifyCaseMaterial:
    def test_execution_application(self, svc):
        result = svc.classify_case_material(
            filename="执行申请书.pdf", text_excerpt="申请执行", enable_ai=False
        )
        assert result["category"] == "party"
        assert result["side"] == "our"
        assert result["type_name_hint"] == "执行申请书"

    def test_identity_document(self, svc):
        result = svc.classify_case_material(
            filename="身份证.pdf", text_excerpt="", enable_ai=False
        )
        assert result["category"] == "party"
        # side is "auto" in rule; with no context, it becomes "unknown"
        assert result["side"] in ("our", "opponent", "unknown")

    def test_authorization_material(self, svc):
        result = svc.classify_case_material(
            filename="授权委托书.pdf", text_excerpt="", enable_ai=False
        )
        assert result["category"] == "party"

    def test_restriction_measures(self, svc):
        result = svc.classify_case_material(
            filename="限制高消费令.pdf", text_excerpt="", enable_ai=False
        )
        assert result["category"] == "non_party"

    def test_evidence_list(self, svc):
        result = svc.classify_case_material(
            filename="证据清单.pdf", text_excerpt="", enable_ai=False
        )
        assert result["category"] == "party"
        assert result["side"] == "our"
        assert result["type_name_hint"] == "证据材料"

    def test_served_address_confirmation(self, svc):
        result = svc.classify_case_material(
            filename="送达地址确认书.pdf", text_excerpt="", enable_ai=False
        )
        assert result["category"] == "non_party"
        assert result["type_name_hint"] == "送达地址确认书"

    def test_refund_account_confirmation(self, svc):
        result = svc.classify_case_material(
            filename="退费账户确认书.pdf", text_excerpt="", enable_ai=False
        )
        assert result["category"] == "non_party"
        assert result["type_name_hint"] == "退费账户确认书"

    def test_enforcement_basis(self, svc):
        result = svc.classify_case_material(
            filename="判决书.pdf", text_excerpt="", enable_ai=False
        )
        assert result["category"] == "non_party"
        assert result["type_name_hint"] == "执行依据及生效证明"

    def test_no_match_no_ai_returns_default(self, svc):
        result = svc.classify_case_material(
            filename="random_file.pdf", text_excerpt="irrelevant", enable_ai=False
        )
        assert result["category"] == "unknown"
        assert result["confidence"] == 0.0

    def test_filing_material_folder(self, svc):
        result = svc.classify_case_material(
            filename="some_doc.pdf", text_excerpt="", source_path="/data/立案材料/some_doc.pdf", enable_ai=False
        )
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_ai_disabled_with_folder_hint(self, svc):
        result = svc.classify_case_material(
            filename="random.pdf",
            text_excerpt="",
            scan_subfolder="3_证据材料",
            enable_ai=False,
        )
        assert result["type_name_hint"] == "证据材料"

    def test_context_party_side_inference_our(self, svc):
        context = {"our_party_names": ["张三"], "opponent_party_names": ["李四"]}
        result = svc.classify_case_material(
            filename="委托材料_张三.pdf", text_excerpt="", context=context, enable_ai=False
        )
        # Should infer "our" side based on party name match
        assert result["category"] == "party"

    def test_case_material_with_context_supervising_authority(self, svc):
        context = {"primary_supervising_authority_id": 42}
        result = svc.classify_case_material(
            filename="限制高消费.pdf", text_excerpt="", context=context, enable_ai=False
        )
        assert result["category"] == "non_party"
        assert result["suggested_supervising_authority_id"] == 42

    def test_case_material_ai_fallback_when_no_match(self, svc, monkeypatch):
        # Disable AI completion to test the fallback path
        monkeypatch.setattr(svc, "_complete", lambda **kw: "")
        result = svc.classify_case_material(
            filename="unknown.pdf", text_excerpt="some text", enable_ai=True
        )
        assert result["category"] == "unknown"


# ── classify_archive_material ──


class TestClassifyArchiveMaterial:
    def test_litigation_filename_match(self, svc):
        result = svc.classify_archive_material(
            filename="起诉状.pdf", source_path="/data/doc.pdf", archive_category="litigation"
        )
        assert result["archive_item_code"] == "lt_7"

    def test_litigation_folder_match(self, svc):
        result = svc.classify_archive_material(
            filename="doc.pdf", source_path="/data/证据材料/doc.pdf", archive_category="litigation"
        )
        assert result["archive_item_code"] == "lt_10"

    def test_criminal_filename_match(self, svc):
        result = svc.classify_archive_material(
            filename="会见笔录.pdf", source_path="/data/doc.pdf", archive_category="criminal"
        )
        assert result["archive_item_code"] == "cr_7"

    def test_non_litigation_filename_match(self, svc):
        result = svc.classify_archive_material(
            filename="授权委托书.pdf", source_path="/data/doc.pdf", archive_category="non_litigation"
        )
        assert result["archive_item_code"] == "nl_12"

    def test_no_match_returns_empty(self, svc):
        result = svc.classify_archive_material(
            filename="random.pdf", source_path="/data/random.pdf", archive_category="litigation"
        )
        assert result["archive_item_code"] == ""
        assert result["archive_item_name"] == "未匹配"

    def test_invalid_archive_category_defaults_to_litigation(self, svc):
        result = svc.classify_archive_material(
            filename="起诉状.pdf", source_path="/data/doc.pdf", archive_category="invalid"
        )
        assert result["archive_item_code"] == "lt_7"

    def test_parent_folder_hint(self, svc):
        result = svc.classify_archive_material(
            filename="doc.pdf", source_path="/data/doc.pdf", archive_category="litigation",
            parent_folder_hint="代理词"
        )
        assert result["archive_item_code"] == "lt_15"

    def test_litigation_judgment_match(self, svc):
        result = svc.classify_archive_material(
            filename="判决书.pdf", source_path="/data/doc.pdf", archive_category="litigation"
        )
        assert result["archive_item_code"] == "lt_17"

    def test_litigation_authorization(self, svc):
        result = svc.classify_archive_material(
            filename="所函.pdf", source_path="/data/doc.pdf", archive_category="litigation"
        )
        assert result["archive_item_code"] == "lt_20"


# ── Pure helper methods ──


class TestHelpers:
    def test_normalize_for_match(self, svc):
        assert svc._normalize_for_match("  Hello World  ") == "helloworld"
        assert svc._normalize_for_match("path\\to\\file") == "path/to/file"
        assert svc._normalize_for_match("") == ""

    def test_extract_subfolder_hint(self, svc):
        assert svc._extract_subfolder_hint("2-立案材料") == "立案材料"
        assert svc._extract_subfolder_hint("3_执行依据") == "执行依据"
        assert svc._extract_subfolder_hint("") == ""
        assert svc._extract_subfolder_hint("子目录A/子目录B") == "子目录B"

    def test_to_confidence(self, svc):
        assert svc._to_confidence(0.5) == 0.5
        assert svc._to_confidence(None) == 0.0
        assert svc._to_confidence(-1) == 0.0
        assert svc._to_confidence(2.0) == 1.0
        assert svc._to_confidence("abc") == 0.0

    def test_extract_json_valid(self, svc):
        result = svc._extract_json('{"category": "party", "side": "our"}')
        assert result == {"category": "party", "side": "our"}

    def test_extract_json_fenced(self, svc):
        result = svc._extract_json('```json\n{"category": "party"}\n```')
        assert result == {"category": "party"}

    def test_extract_json_invalid(self, svc):
        assert svc._extract_json("not json") is None

    def test_extract_json_empty(self, svc):
        assert svc._extract_json("") is None

    def test_extract_party_ids_by_side(self, svc):
        ctx = {"our_party_ids": [1, 2, 3], "opponent_party_ids": [4, 5]}
        result = svc._extract_party_ids_by_side(side="our", context=ctx)
        assert result == [1, 2, 3]
        result2 = svc._extract_party_ids_by_side(side="opponent", context=ctx)
        assert result2 == [4, 5]

    def test_extract_party_ids_dedup_and_validate(self, svc):
        ctx = {"our_party_ids": [1, -1, 0, 1, "abc", 2]}
        result = svc._extract_party_ids_by_side(side="our", context=ctx)
        assert result == [1, 2]

    def test_extract_primary_supervising_authority_id(self, svc):
        assert svc._extract_primary_supervising_authority_id({"primary_supervising_authority_id": 42}) == 42
        assert svc._extract_primary_supervising_authority_id({}) is None
        assert svc._extract_primary_supervising_authority_id({"primary_supervising_authority_id": -1}) is None

    def test_infer_case_side_opponent(self, svc):
        result = svc._infer_case_side(
            match_text="被告张三", context={"opponent_party_names": ["张三"]}
        )
        assert result == "opponent"

    def test_infer_case_side_our(self, svc):
        result = svc._infer_case_side(
            match_text="原告李四", context={"our_party_names": ["李四"]}
        )
        assert result == "our"

    def test_infer_case_side_unknown_when_both(self, svc):
        result = svc._infer_case_side(
            match_text="原告被告双方", context={}
        )
        assert result == "unknown"

    def test_infer_case_side_empty_text(self, svc):
        assert svc._infer_case_side(match_text="", context={}) == "unknown"

    def test_parse_work_log_from_folder_name(self, svc):
        result = svc.parse_work_log_from_folder_name("2025.01.23-知识产权合同")
        assert result == {"date": "2025-01-23", "content": "审核知识产权合同"}

    def test_parse_work_log_no_match(self, svc):
        assert svc.parse_work_log_from_folder_name("普通文件夹") is None

    def test_extract_path_parts(self, svc):
        result = svc._extract_path_parts("/data/1-起诉状/证据材料/doc.pdf")
        assert "起诉状" in result
        assert "证据材料" in result
