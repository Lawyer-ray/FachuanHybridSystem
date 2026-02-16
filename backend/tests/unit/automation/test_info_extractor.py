"""
信息提取器单元测试

测试 InfoExtractor 的基本功能。

Requirements: 4.3, 4.4
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.court_document_recognition import InfoExtractor


class TestInfoExtractor:
    """InfoExtractor 单元测试"""

    def test_init_with_defaults(self):
        """测试使用默认配置初始化"""
        extractor = InfoExtractor()
        assert extractor.ollama_model is not None
        assert extractor.ollama_base_url is not None

    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        extractor = InfoExtractor(ollama_model="custom-model", ollama_base_url="http://custom:11434")
        assert extractor.ollama_model == "custom-model"
        assert extractor.ollama_base_url == "http://custom:11434"

    def test_extract_summons_info_empty_text(self):
        """测试空文本返回空结果"""
        extractor = InfoExtractor()
        result = extractor.extract_summons_info("")
        assert result["case_number"] is None
        assert result["court_time"] is None

    def test_extract_summons_info_whitespace_text(self):
        """测试纯空白文本返回空结果"""
        extractor = InfoExtractor()
        result = extractor.extract_summons_info("   \n\t  ")
        assert result["case_number"] is None
        assert result["court_time"] is None

    def test_extract_execution_info_empty_text(self):
        """测试空文本返回空结果"""
        extractor = InfoExtractor()
        result = extractor.extract_execution_info("")
        assert result["case_number"] is None
        assert result["preservation_deadline"] is None

    @patch("apps.automation.services.court_document_recognition.info_extractor.chat")
    def test_extract_summons_info_success(self, mock_chat):
        """测试成功提取传票信息"""
        mock_chat.return_value = {
            "message": {"content": '{"case_number": "（2024）京0105民初12345号", "court_time": "2024-03-15 09:30"}'}
        }

        extractor = InfoExtractor()
        result = extractor.extract_summons_info("传票内容...")

        assert result["case_number"] == "（2024）京0105民初12345号"
        assert result["court_time"] == datetime(2024, 3, 15, 9, 30)

    @patch("apps.automation.services.court_document_recognition.info_extractor.chat")
    def test_extract_summons_info_with_null_values(self, mock_chat):
        """测试 AI 返回 null 值时的处理"""
        mock_chat.return_value = {"message": {"content": '{"case_number": null, "court_time": null}'}}

        extractor = InfoExtractor()
        result = extractor.extract_summons_info("传票内容...")

        assert result["case_number"] is None
        assert result["court_time"] is None

    @patch("apps.automation.services.court_document_recognition.info_extractor.chat")
    def test_extract_execution_info_success(self, mock_chat):
        """测试成功提取执行裁定书信息"""
        mock_chat.return_value = {
            "message": {
                "content": '{"case_number": "（2024）京0105执保12345号", "preservation_deadline": "2024-06-15"}'
            }
        }

        extractor = InfoExtractor()
        result = extractor.extract_execution_info("执行裁定书内容...")

        assert result["case_number"] == "（2024）京0105执保12345号"
        assert result["preservation_deadline"] == datetime(2024, 6, 15)

    @patch("apps.automation.services.court_document_recognition.info_extractor.chat")
    def test_extract_summons_info_connection_error_fallback(self, mock_chat):
        """测试 Ollama 服务不可用时降级使用正则结果"""
        mock_chat.side_effect = ConnectionError("Ollama 服务不可用")

        extractor = InfoExtractor()
        # 不应该抛出异常，而是返回空结果（因为正则也没有匹配到）
        result = extractor.extract_summons_info("传票内容...")

        assert result["case_number"] is None
        assert result["court_time"] is None
        assert result["extraction_method"] == "无法提取"

    @patch("apps.automation.services.court_document_recognition.info_extractor.chat")
    def test_extract_summons_info_runtime_error_fallback(self, mock_chat):
        """测试其他错误时降级使用正则结果"""
        mock_chat.side_effect = Exception("未知错误")

        extractor = InfoExtractor()
        # 不应该抛出异常，而是返回空结果
        result = extractor.extract_summons_info("传票内容...")

        assert result["case_number"] is None
        assert result["court_time"] is None

    @patch("apps.automation.services.court_document_recognition.info_extractor.chat")
    def test_extract_summons_info_ollama_fail_regex_success(self, mock_chat):
        """测试 Ollama 失败但正则成功时使用正则结果"""
        mock_chat.side_effect = ConnectionError("Ollama 服务不可用")

        extractor = InfoExtractor()
        # 包含可以被正则匹配的时间
        result = extractor.extract_summons_info("开庭时间2025年11月13日9时30分")

        assert result["case_number"] is None  # 案号需要 Ollama 提取
        assert result["court_time"] is not None
        assert result["court_time"].hour == 9
        assert result["court_time"].minute == 30


class TestInfoExtractorParsing:
    """InfoExtractor 解析功能测试"""

    def test_normalize_case_number_full_width_brackets(self):
        """测试全角括号标准化"""
        extractor = InfoExtractor()
        result = extractor._normalize_case_number("(2024)京0105民初12345号")
        assert result == "（2024）京0105民初12345号"

    def test_normalize_case_number_already_standard(self):
        """测试已标准化的案号"""
        extractor = InfoExtractor()
        result = extractor._normalize_case_number("（2024）京0105民初12345号")
        assert result == "（2024）京0105民初12345号"

    def test_parse_datetime_standard_format(self):
        """测试标准日期时间格式解析"""
        extractor = InfoExtractor()
        result = extractor._parse_datetime("2024-03-15 09:30")
        assert result == datetime(2024, 3, 15, 9, 30)

    def test_parse_datetime_chinese_format(self):
        """测试中文日期时间格式解析"""
        extractor = InfoExtractor()
        result = extractor._parse_datetime("2024年03月15日 09:30")
        assert result == datetime(2024, 3, 15, 9, 30)

    def test_parse_datetime_chinese_full_format(self):
        """测试完整中文日期时间格式解析"""
        extractor = InfoExtractor()
        result = extractor._parse_datetime("2024年03月15日 09时30分")
        assert result == datetime(2024, 3, 15, 9, 30)

    def test_parse_datetime_invalid_format(self):
        """测试无效格式返回 None"""
        extractor = InfoExtractor()
        result = extractor._parse_datetime("invalid date")
        assert result is None

    def test_parse_date_standard_format(self):
        """测试标准日期格式解析"""
        extractor = InfoExtractor()
        result = extractor._parse_date("2024-06-15")
        assert result == datetime(2024, 6, 15)

    def test_parse_date_chinese_format(self):
        """测试中文日期格式解析"""
        extractor = InfoExtractor()
        result = extractor._parse_date("2024年06月15日")
        assert result == datetime(2024, 6, 15)

    def test_parse_date_invalid_format(self):
        """测试无效格式返回 None"""
        extractor = InfoExtractor()
        result = extractor._parse_date("invalid date")
        assert result is None

    def test_extract_json_from_response_direct(self):
        """测试直接 JSON 解析"""
        extractor = InfoExtractor()
        result = extractor._extract_json_from_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_from_response_with_text(self):
        """测试从包含额外文本的响应中提取 JSON"""
        extractor = InfoExtractor()
        result = extractor._extract_json_from_response('Some text {"key": "value"} more text')
        assert result == {"key": "value"}

    def test_extract_json_from_response_markdown_block(self):
        """测试从 markdown 代码块中提取 JSON"""
        extractor = InfoExtractor()
        result = extractor._extract_json_from_response('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_extract_json_from_response_invalid(self):
        """测试无效 JSON 返回 None"""
        extractor = InfoExtractor()
        result = extractor._extract_json_from_response("not json at all")
        assert result is None


class TestRegexDatetimeExtraction:
    """正则表达式日期时间提取测试"""

    def test_extract_datetime_ocr_format_no_space(self):
        """测试 OCR 识别格式（无空格）：到庭应到时间2025年11月13日9时15分"""
        extractor = InfoExtractor()
        text = "到庭应到时间2025年11月13日9时15分"
        results = extractor._extract_datetime_by_regex(text)

        assert len(results) >= 1
        dt, matched_text, score = results[0]
        assert dt == datetime(2025, 11, 13, 9, 15)
        assert "2025年11月13日9时15分" in matched_text

    def test_extract_datetime_ocr_format_with_space(self):
        """测试 OCR 识别格式（有空格）：开庭时间 2025年11月13日 9时15分"""
        extractor = InfoExtractor()
        text = "开庭时间 2025年11月13日 9时15分"
        results = extractor._extract_datetime_by_regex(text)

        assert len(results) >= 1
        dt, matched_text, score = results[0]
        assert dt == datetime(2025, 11, 13, 9, 15)

    def test_extract_datetime_with_am_pm(self):
        """测试带上午/下午的格式"""
        extractor = InfoExtractor()

        # 上午
        text1 = "开庭时间2025年11月13日上午9时30分"
        results1 = extractor._extract_datetime_by_regex(text1)
        assert len(results1) >= 1
        assert results1[0][0] == datetime(2025, 11, 13, 9, 30)

        # 下午
        text2 = "开庭时间2025年11月13日下午3时30分"
        results2 = extractor._extract_datetime_by_regex(text2)
        assert len(results2) >= 1
        assert results2[0][0] == datetime(2025, 11, 13, 15, 30)

    def test_extract_datetime_iso_format(self):
        """测试 ISO 格式：2025-11-13 09:15"""
        extractor = InfoExtractor()
        text = "开庭时间 2025-11-13 09:15"
        results = extractor._extract_datetime_by_regex(text)

        assert len(results) >= 1
        dt, matched_text, score = results[0]
        assert dt == datetime(2025, 11, 13, 9, 15)

    def test_extract_datetime_colon_format(self):
        """测试冒号格式：2025年11月13日 9:15"""
        extractor = InfoExtractor()
        text = "开庭时间2025年11月13日 9:15"
        results = extractor._extract_datetime_by_regex(text)

        assert len(results) >= 1
        dt, matched_text, score = results[0]
        assert dt == datetime(2025, 11, 13, 9, 15)

    def test_context_score_high_weight_keywords(self):
        """测试高权重关键词的上下文得分"""
        extractor = InfoExtractor()

        # 包含高权重关键词"开庭"
        text_high = "定于2025年11月13日9时15分开庭审理"
        results_high = extractor._extract_datetime_by_regex(text_high)

        # 不包含关键词
        text_low = "日期2025年11月13日9时15分记录"
        results_low = extractor._extract_datetime_by_regex(text_low)

        assert len(results_high) >= 1
        assert len(results_low) >= 1

        # 高权重关键词应该有更高的得分
        assert results_high[0][2] > results_low[0][2]

    def test_no_false_positive_am_pm(self):
        """测试不会错误匹配非上午/下午的文本"""
        extractor = InfoExtractor()
        # 这个文本中的"9"不应该被误认为是上午/下午标识
        text = "到庭应到时间2025年11月13日9时15分"
        results = extractor._extract_datetime_by_regex(text)

        assert len(results) >= 1
        dt = results[0][0]
        # 应该是 9:15，不是 15:15 或其他错误时间
        assert dt.hour == 9
        assert dt.minute == 15
