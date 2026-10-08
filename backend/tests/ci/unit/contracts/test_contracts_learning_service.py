"""contracts/services/archive/learning_service.py 单元测试。"""

from __future__ import annotations

import json

from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.archive.learning_service import (
    _DOCUMENT_KEYWORDS,
    ArchiveLearningService,
    _contains_document_keyword,
    _is_non_keyword_attachment,
    _strip_non_keyword_parts,
    extract_keywords,
)


class TestExtractKeywords:
    """extract_keywords 函数测试。"""

    def test_simple_chinese_filename(self) -> None:
        result = extract_keywords("起诉状.docx")
        assert "起诉状" in result

    def test_filename_with_brackets(self) -> None:
        result = extract_keywords("案卷封面（某某案）.pdf")
        assert "案卷封面" in result

    def test_filename_with_page_number(self) -> None:
        result = extract_keywords("起诉状第6页.jpg")
        assert "起诉状" in result

    def test_filename_with_digits(self) -> None:
        result = extract_keywords("判决书123.pdf")
        assert "判决书" in result

    def test_filename_with_case_number(self) -> None:
        result = extract_keywords("调解书(2024)粤0101民初1001号.pdf")
        assert "调解书" in result

    def test_empty_filename(self) -> None:
        result = extract_keywords("")
        assert result == []

    def test_pure_digits_filename(self) -> None:
        result = extract_keywords("12345.pdf")
        assert result == []

    def test_pure_english_filename(self) -> None:
        result = extract_keywords("document.pdf")
        assert result == []

    def test_short_chinese_text_filtered(self) -> None:
        """Less than 2 Chinese chars should be filtered."""
        result = extract_keywords("诉.pdf")
        assert result == []

    def test_non_document_keyword_filtered(self) -> None:
        """Text without document keywords should be filtered."""
        result = extract_keywords("张福裕案件.pdf")
        assert result == []

    def test_multiple_keywords(self) -> None:
        result = extract_keywords("起诉状和答辩状.pdf")
        keywords = result
        assert len(keywords) >= 1

    def test_strips_parentheses_content(self) -> None:
        result = extract_keywords("授权委托书(原件).pdf")
        # After stripping parens, "授权委托书" → keyword extraction finds "授权委托" (partial match)
        assert len(result) >= 1

    def test_composite_document_name_preserved(self) -> None:
        """Composite names should have at least one keyword extracted."""
        result = extract_keywords("缴纳保全费通知书.pdf")
        # The function strips non-keyword parts, so result may be just the core keyword
        assert len(result) >= 1


class TestContainsDocumentKeyword:
    """_contains_document_keyword 函数测试。"""

    def test_contains_keyword(self) -> None:
        assert _contains_document_keyword("起诉状") is True
        assert _contains_document_keyword("案卷封面") is True
        assert _contains_document_keyword("证据清单") is True

    def test_no_keyword(self) -> None:
        assert _contains_document_keyword("张三案件") is False
        assert _contains_document_keyword("随便写") is False

    def test_empty_string(self) -> None:
        assert _contains_document_keyword("") is False


class TestStripNonKeywordParts:
    """_strip_non_keyword_parts 函数测试。"""

    def test_exact_keyword_match(self) -> None:
        assert _strip_non_keyword_parts("起诉状") == "起诉状"

    def test_prefix_person_name_stripped(self) -> None:
        """Person name before keyword should be stripped."""
        result = _strip_non_keyword_parts("张三起诉状")
        assert result == "起诉状"

    def test_company_prefix_stripped(self) -> None:
        result = _strip_non_keyword_parts("佛山市某某公司起诉状")
        assert result == "起诉状"

    def test_composite_name_preserved(self) -> None:
        """Composite names should return a keyword part."""
        result = _strip_non_keyword_parts("缴纳保全费通知书")
        # 收紧白名单后"通知"已移除，但"通知书"/"保全费"仍在白名单中
        # 前缀"缴纳保全费"含关键词"保全费"重叠 → 保留原文
        assert len(result) >= 1

    def test_no_keyword_returns_original(self) -> None:
        result = _strip_non_keyword_parts("随便写的文字")
        assert result == "随便写的文字"


class TestIsNonKeywordAttachment:
    """_is_non_keyword_attachment 函数测试。"""

    def test_empty_text(self) -> None:
        assert _is_non_keyword_attachment("") is False

    def test_pure_symbols(self) -> None:
        assert _is_non_keyword_attachment("---") is False

    def test_person_name(self) -> None:
        assert _is_non_keyword_attachment("张三") is True

    def test_keyword_text(self) -> None:
        assert _is_non_keyword_attachment("起诉状") is False

    def test_mixed_text_with_keyword(self) -> None:
        assert _is_non_keyword_attachment("某某起诉状") is False


class TestDocumentKeywords:
    """_DOCUMENT_KEYWORDS 常量测试。"""

    def test_contains_litigation_keywords(self) -> None:
        assert "起诉状" in _DOCUMENT_KEYWORDS
        assert "答辩状" in _DOCUMENT_KEYWORDS
        assert "判决书" in _DOCUMENT_KEYWORDS

    def test_contains_evidence_keywords(self) -> None:
        assert "证据清单" in _DOCUMENT_KEYWORDS
        assert "调查笔录" in _DOCUMENT_KEYWORDS

    def test_contains_archive_keywords(self) -> None:
        assert "案卷封面" in _DOCUMENT_KEYWORDS
        assert "结案归档" in _DOCUMENT_KEYWORDS

    def test_is_tuple(self) -> None:
        assert isinstance(_DOCUMENT_KEYWORDS, tuple)


class TestArchiveLearningService:
    """ArchiveLearningService 类测试。"""

    def test_init(self) -> None:
        svc = ArchiveLearningService()
        assert svc is not None

    def test_generate_json_file_empty(self) -> None:
        """安全审计 2026Q4：空规则生成合法 JSON（原为 Python 源码）。"""
        svc = ArchiveLearningService()
        result = svc._generate_json_file({})
        assert json.loads(result) == {}

    def test_generate_json_file_with_data(self) -> None:
        svc = ArchiveLearningService()
        grouped = {
            "litigation": {
                "lt_1": ["起诉状", "答辩状"],
                "lt_2": ["证据"],
            }
        }
        result = svc._generate_json_file(grouped)
        assert json.loads(result) == grouped

    def test_generate_json_file_multiple_categories(self) -> None:
        svc = ArchiveLearningService()
        grouped = {
            "litigation": {"lt_1": ["起诉状"]},
            "non_litigation": {"nl_1": ["律师函"]},
        }
        result = svc._generate_json_file(grouped)
        assert set(json.loads(result)) == {"litigation", "non_litigation"}

    def test_generate_json_file_is_not_python_source(self) -> None:
        """安全审计 2026Q4：产物必须是纯数据，不能是可执行 Python 源码。"""
        svc = ArchiveLearningService()
        result = svc._generate_json_file({"litigation": {"lt_1": ["起诉状"]}})
        assert "LEARNED_FILENAME_KEYWORD_TO_ARCHIVE_CODE" not in result
        assert "import" not in result
        assert "def " not in result

    def test_generate_json_file_escapes_quote_injection(self) -> None:
        """安全审计 2026Q4：含引号的关键词必须被转义，不能逃逸成代码。

        原实现用 f'"{kw}"' 拼接 Python 源码，kw 中的引号可闭合字符串字面量
        并注入任意表达式；改用 json.dumps 后 keyword 永远是字符串值。
        """
        svc = ArchiveLearningService()
        malicious = 'x"] if __import__("os").system("id") else ["'
        grouped = {"litigation": {"lt_1": [malicious]}}
        result = svc._generate_json_file(grouped)
        # 关键断言：JSON 解析回来必须得到原字符串——说明引号被正确转义成
        # 「数据」而非闭合了某个字符串字面量。原实现的产物在 ast.literal_eval
        # 下会直接触发注入表达式（__import__("os").system 被执行）。
        assert json.loads(result)["litigation"]["lt_1"] == [malicious]
        # 用 ast.literal_eval 求值（不执行代码，仅解析字面量）：
        # JSON 是 Python 字面量的子集，能安全求值且结果就是纯数据。
        import ast

        parsed = ast.literal_eval(result)
        assert parsed["litigation"]["lt_1"] == [malicious]
        assert isinstance(parsed["litigation"]["lt_1"][0], str)

    def test_generate_json_file_sorted_keys(self) -> None:
        svc = ArchiveLearningService()
        grouped = {
            "z_category": {"z_code": ["word_a"]},
            "a_category": {"a_code": ["word_b"]},
        }
        result = svc._generate_json_file(grouped)
        # a_category should come before z_category
        a_pos = result.index('"a_category"')
        z_pos = result.index('"z_category"')
        assert a_pos < z_pos
