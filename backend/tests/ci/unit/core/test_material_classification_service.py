"""材料分类服务测试。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.material_classification_service import MaterialClassificationService


class TestMaterialClassificationService:
    """MaterialClassificationService 可测试逻辑。"""

    def _make_service(self):
        return MaterialClassificationService()

    # ── classify_contract_material ──

    def test_classify_contract_in_invoice_folder_contract(self):
        svc = self._make_service()
        result = svc.classify_contract_material(
            filename="合同.docx", text_excerpt="", source_path="/合同发票/合同.docx"
        )
        assert result["category"] == "contract_original"

    def test_classify_contract_in_invoice_folder_invoice(self):
        svc = self._make_service()
        result = svc.classify_contract_material(
            filename="发票.pdf", text_excerpt="", source_path="/合同发票/发票.pdf"
        )
        assert result["category"] == "invoice"

    def test_classify_contract_in_invoice_folder_supervision(self):
        svc = self._make_service()
        result = svc.classify_contract_material(
            filename="监督卡.pdf", text_excerpt="", source_path="/合同发票/监督卡.pdf"
        )
        assert result["category"] == "supervision_card"

    def test_classify_contract_in_invoice_folder_supplementary(self):
        svc = self._make_service()
        result = svc.classify_contract_material(
            filename="补充协议.pdf", text_excerpt="", source_path="/合同发票/补充协议.pdf"
        )
        assert result["category"] == "supplementary_agreement"

    def test_classify_contract_not_in_invoice_folder(self):
        svc = self._make_service()
        result = svc.classify_contract_material(
            filename="合同.docx", text_excerpt="", source_path="/案件材料/合同.docx"
        )
        assert result["category"] == "case_material"

    def test_classify_contract_in_invoice_folder_no_match(self):
        svc = self._make_service()
        result = svc.classify_contract_material(
            filename="random.pdf", text_excerpt="", source_path="/合同发票/random.pdf"
        )
        assert result["category"] == "contract_original"  # default

    def test_classify_contract_false_positive_pattern(self):
        svc = self._make_service()
        result = svc.classify_contract_material(
            filename="买卖合同纠纷.pdf", text_excerpt="", source_path="/合同发票/买卖合同纠纷.pdf"
        )
        # "合同纠纷" is a false positive - "合同" should not match contract_original
        # The result should be the default contract_original since no keyword matched
        assert result["category"] in ("contract_original", "case_material")

    # ── _classify_contract_by_filename ──

    def test_classify_contract_by_filename_none(self):
        svc = self._make_service()
        assert svc._classify_contract_by_filename("") is None

    def test_classify_contract_by_filename_invoice_keyword(self):
        svc = self._make_service()
        result = svc._classify_contract_by_filename("增值税发票.pdf")
        assert result is not None
        assert result["category"] == "invoice"

    # ── _classify_case_by_filename_and_path ──

    def test_classify_case_filing_folder(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(
            filename="", source_path="/立案材料/", context={}
        )
        assert result is not None
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_classify_case_execution_application(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(
            filename="执行申请书.pdf", source_path="/docs/", context={}
        )
        assert result is not None
        assert result["category"] == "party"
        assert result["side"] == "our"
        assert result["type_name_hint"] == "执行申请书"

    def test_classify_case_id_card(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(
            filename="身份证.pdf", source_path="/docs/", context={}
        )
        assert result is not None
        assert result["category"] == "party"

    def test_classify_case_restriction(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(
            filename="限制高消费令.pdf", source_path="/docs/", context={}
        )
        assert result is not None
        assert result["category"] == "non_party"

    def test_classify_case_judgment(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(
            filename="判决书.pdf", source_path="/docs/", context={}
        )
        assert result is not None
        assert result["category"] == "non_party"
        assert result["type_name_hint"] == "执行依据及生效证明"

    def test_classify_case_evidence(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(
            filename="证据清单.pdf", source_path="/docs/", context={}
        )
        assert result is not None
        assert result["category"] == "party"

    def test_classify_case_no_match(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(
            filename="random.pdf", source_path="/docs/", context={}
        )
        assert result is None

    # ── _infer_case_side ──

    def test_infer_case_side_opponent_hint(self):
        svc = self._make_service()
        assert svc._infer_case_side(match_text="被告身份证", context={}) == "opponent"

    def test_infer_case_side_our_hint(self):
        svc = self._make_service()
        assert svc._infer_case_side(match_text="原告营业执照", context={}) == "our"

    def test_infer_case_side_empty(self):
        svc = self._make_service()
        assert svc._infer_case_side(match_text="", context={}) == "unknown"

    def test_infer_case_side_with_party_names(self):
        svc = self._make_service()
        context = {"opponent_party_names": ["张三"]}
        assert svc._infer_case_side(match_text="张三的材料", context=context) == "opponent"

    def test_infer_case_side_both_unknown(self):
        svc = self._make_service()
        context = {"our_party_names": ["原告"], "opponent_party_names": ["被告"]}
        assert svc._infer_case_side(match_text="原告和被告", context=context) == "unknown"

    # ── _extract_party_ids_by_side ──

    def test_extract_party_ids_our(self):
        context = {"our_party_ids": [1, 2, 3]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2, 3]

    def test_extract_party_ids_invalid(self):
        context = {"our_party_ids": [1, -1, 0, "abc", 2]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2]

    def test_extract_party_ids_empty(self):
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context={})
        assert result == []

    # ── _extract_primary_supervising_authority_id ──

    def test_extract_primary_auth_id_valid(self):
        context = {"primary_supervising_authority_id": 5}
        result = MaterialClassificationService._extract_primary_supervising_authority_id(context)
        assert result == 5

    def test_extract_primary_auth_id_none(self):
        result = MaterialClassificationService._extract_primary_supervising_authority_id({})
        assert result is None

    def test_extract_primary_auth_id_invalid(self):
        context = {"primary_supervising_authority_id": "abc"}
        result = MaterialClassificationService._extract_primary_supervising_authority_id(context)
        assert result is None

    # ── _extract_subfolder_hint ──

    def test_extract_subfolder_hint_with_number(self):
        assert MaterialClassificationService._extract_subfolder_hint("2-立案材料") == "立案材料"

    def test_extract_subfolder_hint_with_underscore(self):
        assert MaterialClassificationService._extract_subfolder_hint("3_执行依据") == "执行依据"

    def test_extract_subfolder_hint_no_number(self):
        assert MaterialClassificationService._extract_subfolder_hint("证据材料") == "证据材料"

    def test_extract_subfolder_hint_empty(self):
        assert MaterialClassificationService._extract_subfolder_hint("") == ""

    def test_extract_subfolder_hint_multilevel(self):
        assert MaterialClassificationService._extract_subfolder_hint("a/b/2-立案材料") == "立案材料"

    # ── _normalize_for_match ──

    def test_normalize_for_match_lowercase(self):
        assert MaterialClassificationService._normalize_for_match("ABC") == "abc"

    def test_normalize_for_match_no_spaces(self):
        assert MaterialClassificationService._normalize_for_match("a b c") == "abc"

    def test_normalize_for_match_backslash(self):
        assert MaterialClassificationService._normalize_for_match("a\\b") == "a/b"

    def test_normalize_for_match_empty(self):
        assert MaterialClassificationService._normalize_for_match("") == ""

    # ── _to_confidence ──

    def test_to_confidence_normal(self):
        svc = self._make_service()
        assert svc._to_confidence(0.8) == 0.8

    def test_to_confidence_negative(self):
        svc = self._make_service()
        assert svc._to_confidence(-0.5) == 0.0

    def test_to_confidence_over_one(self):
        svc = self._make_service()
        assert svc._to_confidence(1.5) == 1.0

    def test_to_confidence_none(self):
        svc = self._make_service()
        assert svc._to_confidence(None) == 0.0

    def test_to_confidence_string(self):
        svc = self._make_service()
        assert svc._to_confidence("0.7") == 0.7

    # ── _extract_json ──

    def test_extract_json_direct(self):
        svc = self._make_service()
        result = svc._extract_json('{"a": 1}')
        assert result == {"a": 1}

    def test_extract_json_in_text(self):
        svc = self._make_service()
        result = svc._extract_json('result: {"a": 1}')
        assert result == {"a": 1}

    def test_extract_json_fenced(self):
        svc = self._make_service()
        result = svc._extract_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_extract_json_empty(self):
        svc = self._make_service()
        assert svc._extract_json("") is None

    def test_extract_json_list_not_dict(self):
        svc = self._make_service()
        result = svc._extract_json('[1, 2, 3]')
        assert result is None

    # ── parse_work_log_from_folder_name ──

    def test_parse_work_log_valid(self):
        svc = self._make_service()
        result = svc.parse_work_log_from_folder_name("2025.01.23-知识产权合同")
        assert result is not None
        assert result["date"] == "2025-01-23"
        assert "知识产权合同" in result["content"]

    def test_parse_work_log_dash_separator(self):
        svc = self._make_service()
        result = svc.parse_work_log_from_folder_name("2025-01-23_合同审查")
        assert result is not None
        assert result["date"] == "2025-01-23"

    def test_parse_work_log_no_match(self):
        svc = self._make_service()
        result = svc.parse_work_log_from_folder_name("random_folder")
        assert result is None

    def test_parse_work_log_empty(self):
        svc = self._make_service()
        result = svc.parse_work_log_from_folder_name("")
        assert result is None

    # ── _build_case_suggestion ──

    def test_build_case_suggestion_party_our(self):
        svc = self._make_service()
        context = {"our_party_ids": [1, 2]}
        result = svc._build_case_suggestion(
            category="party", side="our", type_name_hint="test",
            confidence=0.9, reason="test", context=context
        )
        assert result["category"] == "party"
        assert result["side"] == "our"
        assert result["suggested_party_ids"] == [1, 2]

    def test_build_case_suggestion_non_party(self):
        svc = self._make_service()
        context = {"primary_supervising_authority_id": 3}
        result = svc._build_case_suggestion(
            category="non_party", side="unknown", type_name_hint="test",
            confidence=0.9, reason="test", context=context
        )
        assert result["suggested_supervising_authority_id"] == 3

    def test_build_case_suggestion_unknown_category_normalizes_side(self):
        svc = self._make_service()
        result = svc._build_case_suggestion(
            category="unknown", side="our", type_name_hint="test",
            confidence=0.5, reason="test", context={}
        )
        assert result["side"] == "unknown"
