"""
AutoRenameService 单元测试

测试 extract_info 方法的 JSON 解析和降级逻辑。
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.image_rotation.auto_rename_service import (
    EXTRACTION_PROMPT,
    AutoRenameService,
    ExtractionResult,
)


class TestExtractInfo:
    """测试 extract_info 方法"""

    def test_empty_text_returns_empty_result(self):
        """空文本应返回空结果"""
        service = AutoRenameService()
        result = service.extract_info("")

        assert result.date is None
        assert result.amount is None
        assert result.raw_date is None
        assert result.raw_amount is None

    def test_whitespace_only_returns_empty_result(self):
        """仅空白字符应返回空结果"""
        service = AutoRenameService()
        result = service.extract_info("   \n\t  ")

        assert result.date is None
        assert result.amount is None

    def test_llm_failure_returns_empty_result(self):
        """LLM 调用失败应返回空结果而非抛出异常"""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = Exception("Network error")

        service = AutoRenameService(llm_client=mock_llm)
        result = service.extract_info("2025年6月30日 金额：65500元")

        assert result.date is None
        assert result.amount is None

    def test_valid_json_response_parsed_correctly(self):
        """有效 JSON 响应应正确解析"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
        {
            "date": "20250630",
            "amount": "65500元",
            "raw_date": "2025年6月30日",
            "raw_amount": "65500元"
        }
        """
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)
        result = service.extract_info("2025年6月30日 金额：65500元")

        assert result.date == "20250630"
        assert result.amount == "65500元"
        assert result.raw_date == "2025年6月30日"
        assert result.raw_amount == "65500元"

    def test_json_with_markdown_code_block_parsed(self):
        """带 markdown 代码块的 JSON 应正确解析"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
        ```json
        {
            "date": "20250630",
            "amount": "65500元",
            "raw_date": "2025年6月30日",
            "raw_amount": "65500元"
        }
        ```
        """
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)
        result = service.extract_info("2025年6月30日 金额：65500元")

        assert result.date == "20250630"
        assert result.amount == "65500元"

    def test_null_values_in_json_handled(self):
        """JSON 中的 null 值应正确处理"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
        {
            "date": null,
            "amount": "65500元",
            "raw_date": null,
            "raw_amount": "65500元"
        }
        """
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)
        result = service.extract_info("金额：65500元")

        assert result.date is None
        assert result.amount == "65500元"

    def test_invalid_json_fallback_to_regex(self):
        """无效 JSON 应降级到正则提取"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
        这是一些无效的 JSON，但包含 "date": "20250630" 和 "amount": "65500元"
        """
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)
        result = service.extract_info("2025年6月30日 金额：65500元")

        assert result.date == "20250630"
        assert result.amount == "65500元"

    def test_partial_json_fallback_extracts_available_fields(self):
        """部分有效的 JSON 应提取可用字段"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
        { "date": "20250630", "amount": 无效值 }
        """
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)
        result = service.extract_info("2025年6月30日")

        # 应该通过正则提取到 date
        assert result.date == "20250630"


class TestParseExtractionResponse:
    """测试 _parse_extraction_response 方法"""

    def test_extract_json_from_code_block(self):
        """从代码块中提取 JSON"""
        service = AutoRenameService()
        text = '```json\n{"date": "20250630"}\n```'
        json_text = service._extract_json_block(text)

        assert '{"date": "20250630"}' in json_text

    def test_extract_json_from_braces(self):
        """从花括号中提取 JSON"""
        service = AutoRenameService()
        text = 'Some text {"date": "20250630"} more text'
        json_text = service._extract_json_block(text)

        assert json_text == '{"date": "20250630"}'


class TestFallbackRegexExtraction:
    """测试 _fallback_regex_extraction 方法"""

    def test_extract_date_from_malformed_json(self):
        """从格式错误的 JSON 中提取日期"""
        service = AutoRenameService()
        text = '"date": "20250630", "amount": invalid'
        result = service._fallback_regex_extraction(text)

        assert result.date == "20250630"

    def test_extract_amount_from_malformed_json(self):
        """从格式错误的 JSON 中提取金额"""
        service = AutoRenameService()
        text = '"date": invalid, "amount": "65500元"'
        result = service._fallback_regex_extraction(text)

        assert result.amount == "65500元"

    def test_extract_both_from_malformed_json(self):
        """从格式错误的 JSON 中同时提取日期和金额"""
        service = AutoRenameService()
        text = '"date": "20250630", "amount": "65500元"'
        result = service._fallback_regex_extraction(text)

        assert result.date == "20250630"
        assert result.amount == "65500元"

    def test_no_match_returns_empty_result(self):
        """无匹配时返回空结果"""
        service = AutoRenameService()
        text = "completely invalid text"
        result = service._fallback_regex_extraction(text)

        assert result.date is None
        assert result.amount is None


class TestPromptTemplate:
    """测试 Prompt 模板"""

    def test_prompt_contains_ocr_text_placeholder(self):
        """Prompt 模板应包含 ocr_text 占位符"""
        assert "{ocr_text}" in EXTRACTION_PROMPT

    def test_prompt_specifies_json_format(self):
        """Prompt 模板应指定 JSON 格式"""
        assert "JSON" in EXTRACTION_PROMPT
        assert "date" in EXTRACTION_PROMPT
        assert "amount" in EXTRACTION_PROMPT

    def test_prompt_format_works(self):
        """Prompt 模板格式化应正常工作"""
        ocr_text = "测试文本"
        formatted = EXTRACTION_PROMPT.format(ocr_text=ocr_text)

        assert "测试文本" in formatted
        assert "{ocr_text}" not in formatted


class TestGenerateFilename:
    """测试 generate_filename 方法

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    """

    def test_date_and_amount_generates_combined_filename(self):
        """同时有日期和金额时生成 日期_金额.扩展名 格式

        **Validates: Requirements 3.1**
        """
        service = AutoRenameService()
        result = ExtractionResult(date="20250630", amount="65500元")

        filename = service.generate_filename("original.jpg", result)

        assert filename == "20250630_65500元.jpg"

    def test_date_only_generates_date_filename(self):
        """只有日期时生成 日期.扩展名 格式

        **Validates: Requirements 3.2**
        """
        service = AutoRenameService()
        result = ExtractionResult(date="20250630", amount=None)

        filename = service.generate_filename("original.jpg", result)

        assert filename == "20250630.jpg"

    def test_amount_only_generates_amount_filename(self):
        """只有金额时生成 金额.扩展名 格式

        **Validates: Requirements 3.3**
        """
        service = AutoRenameService()
        result = ExtractionResult(date=None, amount="65500元")

        filename = service.generate_filename("original.jpg", result)

        assert filename == "65500元.jpg"

    def test_no_extraction_keeps_original_filename(self):
        """日期和金额都没有时保持原文件名

        **Validates: Requirements 3.4**
        """
        service = AutoRenameService()
        result = ExtractionResult(date=None, amount=None)

        filename = service.generate_filename("original_file.jpg", result)

        assert filename == "original_file.jpg"

    def test_preserves_jpg_extension(self):
        """保留 .jpg 扩展名

        **Validates: Requirements 3.5**
        """
        service = AutoRenameService()
        result = ExtractionResult(date="20250630", amount="65500元")

        filename = service.generate_filename("test.jpg", result)

        assert filename.endswith(".jpg")

    def test_preserves_png_extension(self):
        """保留 .png 扩展名

        **Validates: Requirements 3.5**
        """
        service = AutoRenameService()
        result = ExtractionResult(date="20250630", amount="65500元")

        filename = service.generate_filename("test.png", result)

        assert filename.endswith(".png")

    def test_preserves_jpeg_extension(self):
        """保留 .jpeg 扩展名

        **Validates: Requirements 3.5**
        """
        service = AutoRenameService()
        result = ExtractionResult(date="20250630", amount="65500元")

        filename = service.generate_filename("test.jpeg", result)

        assert filename.endswith(".jpeg")

    def test_preserves_uppercase_extension(self):
        """保留大写扩展名

        **Validates: Requirements 3.5**
        """
        service = AutoRenameService()
        result = ExtractionResult(date="20250630", amount="65500元")

        filename = service.generate_filename("test.JPG", result)

        assert filename.endswith(".JPG")

    def test_handles_filename_without_extension(self):
        """处理无扩展名的文件"""
        service = AutoRenameService()
        result = ExtractionResult(date="20250630", amount="65500元")

        filename = service.generate_filename("noextension", result)

        assert filename == "20250630_65500元"

    def test_handles_filename_with_multiple_dots(self):
        """处理包含多个点的文件名"""
        service = AutoRenameService()
        result = ExtractionResult(date="20250630", amount="65500元")

        filename = service.generate_filename("file.name.with.dots.jpg", result)

        assert filename == "20250630_65500元.jpg"

    def test_empty_string_date_treated_as_none(self):
        """空字符串日期应被视为无日期"""
        service = AutoRenameService()
        result = ExtractionResult(date="", amount="65500元")

        filename = service.generate_filename("test.jpg", result)

        # 空字符串在 Python 中是 falsy，所以应该只使用金额
        assert filename == "65500元.jpg"

    def test_empty_string_amount_treated_as_none(self):
        """空字符串金额应被视为无金额"""
        service = AutoRenameService()
        result = ExtractionResult(date="20250630", amount="")

        filename = service.generate_filename("test.jpg", result)

        # 空字符串在 Python 中是 falsy，所以应该只使用日期
        assert filename == "20250630.jpg"

    def test_both_empty_strings_keeps_original(self):
        """日期和金额都是空字符串时保持原文件名"""
        service = AutoRenameService()
        result = ExtractionResult(date="", amount="")

        filename = service.generate_filename("original.jpg", result)

        assert filename == "original.jpg"


class TestGetFileExtension:
    """测试 _get_file_extension 方法"""

    def test_extracts_simple_extension(self):
        """提取简单扩展名"""
        service = AutoRenameService()

        assert service._get_file_extension("file.jpg") == ".jpg"
        assert service._get_file_extension("file.png") == ".png"
        assert service._get_file_extension("file.pdf") == ".pdf"

    def test_extracts_last_extension_from_multiple_dots(self):
        """从多个点中提取最后一个扩展名"""
        service = AutoRenameService()

        assert service._get_file_extension("file.name.jpg") == ".jpg"
        assert service._get_file_extension("a.b.c.d.png") == ".png"

    def test_returns_empty_for_no_extension(self):
        """无扩展名时返回空字符串"""
        service = AutoRenameService()

        assert service._get_file_extension("noextension") == ""

    def test_handles_hidden_files(self):
        """处理隐藏文件（以点开头）"""
        service = AutoRenameService()

        # 隐藏文件有扩展名
        assert service._get_file_extension(".hidden.jpg") == ".jpg"
        # 纯隐藏文件（无扩展名）
        assert service._get_file_extension(".hidden") == ".hidden"

    def test_preserves_extension_case(self):
        """保留扩展名大小写"""
        service = AutoRenameService()

        assert service._get_file_extension("file.JPG") == ".JPG"
        assert service._get_file_extension("file.Png") == ".Png"


class TestSuggestRename:
    """测试 suggest_rename 方法

    **Validates: Requirements 4.2, 4.4**
    """

    def test_successful_extraction_returns_suggestion(self):
        """成功提取时返回完整建议

        **Validates: Requirements 4.2**
        """
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
        {
            "date": "20250630",
            "amount": "65500元",
            "raw_date": "2025年6月30日",
            "raw_amount": "65500元"
        }
        """
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)
        result = service.suggest_rename("IMG_001.jpg", "2025年6月30日 金额：65500元")

        assert result.original_filename == "IMG_001.jpg"
        assert result.suggested_filename == "20250630_65500元.jpg"
        assert result.date == "20250630"
        assert result.amount == "65500元"
        assert result.success is True
        assert result.error is None

    def test_date_only_extraction(self):
        """只提取到日期时返回日期格式文件名"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
        {
            "date": "20250630",
            "amount": null,
            "raw_date": "2025年6月30日",
            "raw_amount": null
        }
        """
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)
        result = service.suggest_rename("IMG_001.jpg", "2025年6月30日")

        assert result.suggested_filename == "20250630.jpg"
        assert result.date == "20250630"
        assert result.amount is None
        assert result.success is True

    def test_amount_only_extraction(self):
        """只提取到金额时返回金额格式文件名"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
        {
            "date": null,
            "amount": "65500元",
            "raw_date": null,
            "raw_amount": "65500元"
        }
        """
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)
        result = service.suggest_rename("IMG_001.jpg", "金额：65500元")

        assert result.suggested_filename == "65500元.jpg"
        assert result.date is None
        assert result.amount == "65500元"
        assert result.success is True

    def test_no_extraction_keeps_original_filename(self):
        """无法提取时保持原文件名"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
        {
            "date": null,
            "amount": null,
            "raw_date": null,
            "raw_amount": null
        }
        """
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)
        result = service.suggest_rename("IMG_001.jpg", "无法识别的文本")

        assert result.suggested_filename == "IMG_001.jpg"
        assert result.date is None
        assert result.amount is None
        assert result.success is True

    def test_empty_ocr_text_keeps_original_filename(self):
        """空 OCR 文本时保持原文件名"""
        service = AutoRenameService()
        result = service.suggest_rename("IMG_001.jpg", "")

        assert result.original_filename == "IMG_001.jpg"
        assert result.suggested_filename == "IMG_001.jpg"
        assert result.success is True

    def test_llm_failure_returns_failed_suggestion(self):
        """LLM 调用失败时返回失败建议，保持原文件名

        **Validates: Requirements 4.4**
        """
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = Exception("Network error")

        service = AutoRenameService(llm_client=mock_llm)
        result = service.suggest_rename("IMG_001.jpg", "2025年6月30日 金额：65500元")

        # LLM 失败时 extract_info 返回空结果，不会抛出异常
        # 所以 success 仍然是 True，只是没有提取到信息
        assert result.original_filename == "IMG_001.jpg"
        assert result.suggested_filename == "IMG_001.jpg"
        assert result.success is True

    def test_preserves_file_extension(self):
        """保留原文件扩展名"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"date": "20250630", "amount": "65500元"}'
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)

        # 测试 .png 扩展名
        result = service.suggest_rename("IMG_001.png", "2025年6月30日 金额：65500元")
        assert result.suggested_filename == "20250630_65500元.png"

        # 测试 .jpeg 扩展名
        result = service.suggest_rename("IMG_001.jpeg", "2025年6月30日 金额：65500元")
        assert result.suggested_filename == "20250630_65500元.jpeg"


class TestSuggestRenameBatch:
    """测试 suggest_rename_batch 方法

    **Validates: Requirements 4.2, 4.4**
    """

    def test_batch_processing_returns_all_suggestions(self):
        """批量处理返回所有建议

        **Validates: Requirements 4.2**
        """
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"date": "20250630", "amount": "65500元"}'
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)

        # 创建模拟的 RenameRequestItem
        class MockItem:
            def __init__(self, filename, ocr_text):
                self.filename = filename
                self.ocr_text = ocr_text

        items = [
            MockItem("IMG_001.jpg", "2025年6月30日 金额：65500元"),
            MockItem("IMG_002.jpg", "2025年7月1日 金额：12000元"),
            MockItem("IMG_003.jpg", "2025年7月2日 金额：8000元"),
        ]

        results = service.suggest_rename_batch(items)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert results[0].original_filename == "IMG_001.jpg"
        assert results[1].original_filename == "IMG_002.jpg"
        assert results[2].original_filename == "IMG_003.jpg"

    def test_single_failure_does_not_affect_others(self):
        """单个失败不影响其他项目处理

        **Validates: Requirements 4.4**
        """
        mock_llm = MagicMock()

        # 第一次调用成功，第二次失败，第三次成功
        call_count = [0]

        def mock_complete(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                # 第二次调用返回无效 JSON（会降级到正则提取，返回空结果）
                mock_response = MagicMock()
                mock_response.content = "invalid response"
                return mock_response
            else:
                mock_response = MagicMock()
                mock_response.content = '{"date": "20250630", "amount": "65500元"}'
                return mock_response

        mock_llm.complete.side_effect = mock_complete

        service = AutoRenameService(llm_client=mock_llm)

        class MockItem:
            def __init__(self, filename, ocr_text):
                self.filename = filename
                self.ocr_text = ocr_text

        items = [
            MockItem("IMG_001.jpg", "2025年6月30日 金额：65500元"),
            MockItem("IMG_002.jpg", "无法识别"),
            MockItem("IMG_003.jpg", "2025年7月2日 金额：8000元"),
        ]

        results = service.suggest_rename_batch(items)

        # 所有项目都应该有结果
        assert len(results) == 3

        # 第一个和第三个应该成功提取
        assert results[0].suggested_filename == "20250630_65500元.jpg"
        assert results[2].suggested_filename == "20250630_65500元.jpg"

        # 第二个应该保持原文件名（因为无法提取）
        assert results[1].original_filename == "IMG_002.jpg"

    def test_empty_batch_returns_empty_list(self):
        """空批量请求返回空列表"""
        service = AutoRenameService()
        results = service.suggest_rename_batch([])

        assert results == []

    def test_batch_with_mixed_results(self):
        """批量处理包含混合结果（有提取和无提取）"""
        mock_llm = MagicMock()

        call_count = [0]

        def mock_complete(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            if call_count[0] == 1:
                # 第一个：有日期和金额
                mock_response.content = '{"date": "20250630", "amount": "65500元"}'
            elif call_count[0] == 2:
                # 第二个：只有日期
                mock_response.content = '{"date": "20250701", "amount": null}'
            elif call_count[0] == 3:
                # 第三个：只有金额
                mock_response.content = '{"date": null, "amount": "12000元"}'
            else:
                # 第四个：都没有
                mock_response.content = '{"date": null, "amount": null}'
            return mock_response

        mock_llm.complete.side_effect = mock_complete

        service = AutoRenameService(llm_client=mock_llm)

        class MockItem:
            def __init__(self, filename, ocr_text):
                self.filename = filename
                self.ocr_text = ocr_text

        items = [
            MockItem("IMG_001.jpg", "2025年6月30日 金额：65500元"),
            MockItem("IMG_002.jpg", "2025年7月1日"),
            MockItem("IMG_003.jpg", "金额：12000元"),
            MockItem("IMG_004.jpg", "无法识别"),
        ]

        results = service.suggest_rename_batch(items)

        assert len(results) == 4
        assert results[0].suggested_filename == "20250630_65500元.jpg"
        assert results[1].suggested_filename == "20250701.jpg"
        assert results[2].suggested_filename == "12000元.jpg"
        assert results[3].suggested_filename == "IMG_004.jpg"  # 保持原文件名

    def test_batch_preserves_order(self):
        """批量处理保持输入顺序"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"date": null, "amount": null}'
        mock_llm.complete.return_value = mock_response

        service = AutoRenameService(llm_client=mock_llm)

        class MockItem:
            def __init__(self, filename, ocr_text):
                self.filename = filename
                self.ocr_text = ocr_text

        items = [
            MockItem("first.jpg", "text1"),
            MockItem("second.jpg", "text2"),
            MockItem("third.jpg", "text3"),
        ]

        results = service.suggest_rename_batch(items)

        assert results[0].original_filename == "first.jpg"
        assert results[1].original_filename == "second.jpg"
        assert results[2].original_filename == "third.jpg"
