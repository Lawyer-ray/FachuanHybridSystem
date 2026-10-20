"""材料分类服务测试。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.material_classification_service import (
    MaterialClassificationService,
    _extract_json,
    _extract_party_ids_by_side,
    _extract_primary_supervising_authority_id,
    _extract_subfolder_hint,
    _normalize_for_match,
)


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
        result = svc.classify_contract_material(filename="发票.pdf", text_excerpt="", source_path="/合同发票/发票.pdf")
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
            filename="起诉状.docx", text_excerpt="", source_path="/案件材料/起诉状.docx"
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
        result = svc._classify_case_by_filename_and_path(filename="", source_path="/立案材料/", context={})
        assert result is not None
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_classify_case_execution_application(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(filename="执行申请书.pdf", source_path="/docs/", context={})
        assert result is not None
        assert result["category"] == "party"
        assert result["side"] == "our"
        assert result["type_name_hint"] == "执行申请书"

    def test_classify_case_id_card(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(filename="身份证.pdf", source_path="/docs/", context={})
        assert result is not None
        assert result["category"] == "party"

    def test_classify_case_restriction(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(filename="限制高消费令.pdf", source_path="/docs/", context={})
        assert result is not None
        assert result["category"] == "non_party"

    def test_classify_case_judgment(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(filename="判决书.pdf", source_path="/docs/", context={})
        assert result is not None
        assert result["category"] == "non_party"
        assert result["type_name_hint"] == "执行依据及生效证明"

    def test_classify_case_evidence(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(filename="证据清单.pdf", source_path="/docs/", context={})
        assert result is not None
        assert result["category"] == "party"

    def test_classify_case_no_match(self):
        svc = self._make_service()
        result = svc._classify_case_by_filename_and_path(filename="random.pdf", source_path="/docs/", context={})
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
        result = _extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2, 3]

    def test_extract_party_ids_invalid(self):
        context = {"our_party_ids": [1, -1, 0, "abc", 2]}
        result = _extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2]

    def test_extract_party_ids_empty(self):
        result = _extract_party_ids_by_side(side="our", context={})
        assert result == []

    # ── _extract_primary_supervising_authority_id ──

    def test_extract_primary_auth_id_valid(self):
        context = {"primary_supervising_authority_id": 5}
        result = _extract_primary_supervising_authority_id(context)
        assert result == 5

    def test_extract_primary_auth_id_none(self):
        result = _extract_primary_supervising_authority_id({})
        assert result is None

    def test_extract_primary_auth_id_invalid(self):
        context = {"primary_supervising_authority_id": "abc"}
        result = _extract_primary_supervising_authority_id(context)
        assert result is None

    # ── _extract_subfolder_hint ──

    def test_extract_subfolder_hint_with_number(self):
        assert _extract_subfolder_hint("2-立案材料") == "立案材料"

    def test_extract_subfolder_hint_with_underscore(self):
        assert _extract_subfolder_hint("3_执行依据") == "执行依据"

    def test_extract_subfolder_hint_no_number(self):
        assert _extract_subfolder_hint("证据材料") == "证据材料"

    def test_extract_subfolder_hint_empty(self):
        assert _extract_subfolder_hint("") == ""

    def test_extract_subfolder_hint_multilevel(self):
        assert _extract_subfolder_hint("a/b/2-立案材料") == "立案材料"

    # ── _normalize_for_match ──

    def test_normalize_for_match_lowercase(self):
        assert _normalize_for_match("ABC") == "abc"

    def test_normalize_for_match_no_spaces(self):
        assert _normalize_for_match("a b c") == "abc"

    def test_normalize_for_match_backslash(self):
        assert _normalize_for_match("a\\b") == "a/b"

    def test_normalize_for_match_empty(self):
        assert _normalize_for_match("") == ""

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
        result = _extract_json('{"a": 1}')
        assert result == {"a": 1}

    def test_extract_json_in_text(self):
        svc = self._make_service()
        result = _extract_json('result: {"a": 1}')
        assert result == {"a": 1}

    def test_extract_json_fenced(self):
        svc = self._make_service()
        result = _extract_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_extract_json_empty(self):
        svc = self._make_service()
        assert _extract_json("") is None

    def test_extract_json_list_not_dict(self):
        svc = self._make_service()
        result = _extract_json("[1, 2, 3]")
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
            category="party", side="our", type_name_hint="test", confidence=0.9, reason="test", context=context
        )
        assert result["category"] == "party"
        assert result["side"] == "our"
        assert result["suggested_party_ids"] == [1, 2]

    def test_build_case_suggestion_non_party(self):
        svc = self._make_service()
        context = {"primary_supervising_authority_id": 3}
        result = svc._build_case_suggestion(
            category="non_party", side="unknown", type_name_hint="test", confidence=0.9, reason="test", context=context
        )
        assert result["suggested_supervising_authority_id"] == 3

    def test_build_case_suggestion_unknown_category_normalizes_side(self):
        svc = self._make_service()
        result = svc._build_case_suggestion(
            category="unknown", side="our", type_name_hint="test", confidence=0.5, reason="test", context={}
        )
        assert result["side"] == "unknown"


class TestContractInvoiceFolderSegmentMatching:
    """「合同发票」文件夹判定回归：按文件夹名分段匹配，不做整路径子串匹配。

    2026-10-20 合同 8 事故：绑定根目录名含案由"…买卖合同纠纷一案"，
    旧实现对整个绝对路径做裸"合同"子串匹配，导致一审子目录下
    38 个文件全部被误判为"位于合同发票文件夹，默认为合同正本"。
    """

    def _make_service(self):
        return MaterialClassificationService()

    def test_case_name_with_cause_in_root_not_contract_folder(self):
        """根目录名含案由"买卖合同纠纷"时，一审材料不得判入合同发票区域。"""
        svc = self._make_service()
        result = svc.classify_contract_material(
            filename="2-起诉状（某甲公司诉某乙公司、张某买卖合同纠纷一案）V1_20250918.pdf",
            text_excerpt="",
            source_path=(
                "/Users/x/新工作/200-诉讼/1-民商事/2025.08.27-甲公司诉乙公司、"
                "张某买卖合同纠纷一案/1-一审/2-立案材料/1-起诉状/2-起诉状.pdf"
            ),
        )
        assert result["category"] == "case_material"

    def test_filename_with_contract_word_outside_contract_folder(self):
        """文件名含"合同"但不在合同区文件夹 → 案件材料（旧实现被整路径子串误判）。"""
        svc = self._make_service()
        result = svc.classify_contract_material(
            filename="业务合同_20250901邮寄.pdf",
            text_excerpt="",
            source_path="/data/案卷/4-邮件往来/2025.08.31-收到客户邮寄的合同/业务合同_20250901邮寄.pdf",
        )
        assert result["category"] == "case_material"

    def test_dated_folder_ending_with_contract_is_not_exact_folder(self):
        """日期+事项名文件夹（如"2025.08.31-收到客户邮寄的合同"）不整名等于关键词。"""
        svc = self._make_service()
        assert svc._is_contract_invoice_folder("/data/2025.08.31-收到客户邮寄的合同/a.pdf") is False

    def test_numbered_contract_folder_matches_exact(self):
        """数字前缀文件夹 "1-合同" 剥离前缀后整名相等 → 合同区。"""
        svc = self._make_service()
        assert svc._is_contract_invoice_folder("/data/binding/1-合同/委托代理合同.pdf") is True

    def test_numbered_invoice_and_card_folders_match(self):
        svc = self._make_service()
        assert svc._is_contract_invoice_folder("/data/binding/3-发票/发票.pdf") is True
        assert svc._is_contract_invoice_folder("/data/binding/4-监督卡/监督卡.pdf") is True
        assert svc._is_contract_invoice_folder("/data/binding/2-补充协议/补充协议.pdf") is True

    def test_combo_keyword_folder_matches_by_containment(self):
        """组合词"合同发票"允许包含式命中（如"1-合同发票（正本）"）。"""
        svc = self._make_service()
        assert svc._is_contract_invoice_folder("/data/binding/1-合同发票（正本）/合同.pdf") is True
        assert svc._is_contract_invoice_folder("/data/合同及发票/合同.pdf") is True

    def test_contract_original_folder_name_matches(self):
        svc = self._make_service()
        assert svc._is_contract_invoice_folder("/data/binding/1-合同正本/合同.pdf") is True

    def test_trailing_slash_folder_path_is_all_folders(self):
        """尾斜杠路径（无文件名段）全部按文件夹判定。"""
        svc = self._make_service()
        assert svc._is_contract_invoice_folder("/合同发票/") is True
        assert svc._is_contract_invoice_folder("/案件材料/") is False

    def test_windows_style_path_segments(self):
        svc = self._make_service()
        assert svc._is_contract_invoice_folder("C:\\data\\1-合同\\合同.pdf") is True
        assert svc._is_contract_invoice_folder("C:\\data\\1-一审\\起诉状.pdf") is False

    def test_litigation_subfolders_not_contract_area(self):
        """诉讼一审各子文件夹均不得命中合同区（覆盖真实目录形态）。"""
        svc = self._make_service()
        subfolders = [
            "/root/买卖合同纠纷一案/1-一审/2-立案材料/1-起诉状/起诉状.pdf",
            "/root/买卖合同纠纷一案/1-一审/2-立案材料/2-委托授权材料/授权委托书.pdf",
            "/root/买卖合同纠纷一案/1-一审/2-立案材料/4-主要证据材料/证据明细.pdf",
            "/root/买卖合同纠纷一案/1-一审/4-邮件往来及电话录音/2025.11.05-交费通知/通知书.pdf",
        ]
        for path in subfolders:
            assert svc._is_contract_invoice_folder(path) is False, path
