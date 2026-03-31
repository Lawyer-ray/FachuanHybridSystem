"""Business logic services."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

"""
财产保全日期识别服务

负责从法院文书中识别并提取保全措施的到期时间.
支持 PDF 文件和纯文本输入,使用大模型(优先 Ollama,降级 SiliconFlow)进行智能识别.

Requirements: 1.5, 1.6, 2.1, 6.1, 6.2, 6.4
"""


import json
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from apps.core.exceptions import ValidationException

from .models import PreservationExtractionResult, PreservationMeasure, ReminderData
from .prompts import DEFAULT_PENDING_NOTE, PENDING_KEYWORDS, PRESERVATION_DATE_EXTRACTION_PROMPT
from .validators import MeasureValidator

if TYPE_CHECKING:
    from apps.document_recognition.services import TextExtractionService

logger = logging.getLogger("apps.preservation_date")


class PreservationDateExtractionService:
    """
    财产保全日期识别服务

    协调整个识别流程:
    1. 从 PDF 文件中提取文本(复用 TextExtractionService)
    2. 使用大模型分析文本(优先 Ollama,降级 SiliconFlow)
    3. 解析大模型返回的 JSON
    4. 将结果转换为 Reminder 格式

    Requirements: 1.5, 1.6, 2.1, 6.1, 6.2, 6.4
    """

    def __init__(
        self,
        text_service: TextExtractionService | None = None,
    ) -> None:
        """
        初始化服务

        Args:
            text_service: 文本提取服务,None 时延迟加载
        """
        self._text_service = text_service
        self._validator = MeasureValidator()

    @property
    def text_service(self) -> TextExtractionService:
        """延迟加载文本提取服务,不限制提取字数"""
        if self._text_service is None:
            from apps.document_recognition.services import TextExtractionService

            # 传入一个很大的值来绕过默认限制
            self._text_service = TextExtractionService(text_limit=100000)
        return self._text_service

    def extract_from_file(self, file_path: str) -> PreservationExtractionResult:
        """
        从 PDF 文件中提取财产保全日期

        Args:
            file_path: PDF 文件路径

        Returns:
            PreservationExtractionResult: 提取结果

        Requirements: 1.5, 1.6
        """
        # 提取文本
        try:
            text_result = self.text_service.extract_text(file_path)
        except ValidationException:
            raise
        except Exception as e:
            logger.error(f"文本提取失败: {e}")
            return PreservationExtractionResult(
                success=False,
                error=f"文件读取失败: {e!s}",
                extraction_method="unknown",
            )

        if not text_result.success or not text_result.text:
            return PreservationExtractionResult(
                success=False,
                error="无法从文件中提取文本",
                extraction_method=text_result.extraction_method,
            )

        # 记录提取的文本内容
        logger.info(f"提取的文本内容:\n{text_result.text}")

        # 调用文本提取方法
        result = self.extract_from_text(text_result.text)
        result.extraction_method = text_result.extraction_method
        return result

    def extract_from_text(self, text: str) -> PreservationExtractionResult:
        """
        从文本中提取财产保全日期

        Args:
            text: 文书文本内容

        Returns:
            PreservationExtractionResult: 提取结果

        Requirements: 2.1
        """
        if not text or not text.strip():
            return PreservationExtractionResult(
                success=False,
                error="输入文本为空",
            )

        # 预处理文本
        text = self._preprocess_text(text)

        # 调用大模型
        try:
            llm_response, model_used = self._call_llm(text)
            logger.info(f"大模型调用成功,模型: {model_used}, 响应长度: {len(llm_response)}")
            logger.debug(f"大模型原始响应: {llm_response[:1000]}")
        except Exception as e:
            logger.error(f"大模型调用失败: {e}", exc_info=True)
            return PreservationExtractionResult(
                success=False,
                error=f"大模型调用失败: {e!s},请检查模型配置",
            )

        # 解析响应
        try:
            measures = self._parse_llm_response(llm_response)
        except Exception as e:
            logger.warning(f"JSON 解析失败: {e}, 原始响应: {llm_response[:500]}")
            return PreservationExtractionResult(
                success=False,
                error=f"大模型返回格式异常: {e!s}",
                model_used=model_used,
                raw_response=llm_response,
            )

        # 检查是否找到保全措施
        if not measures:
            return PreservationExtractionResult(
                success=True,
                measures=[],
                reminders=[],
                model_used=model_used,
                raw_response=llm_response,
                error="文书中未找到保全措施",
            )

        # 法律约束校验
        measures = self._validator.validate_all(measures)

        # 转换为 Reminder 格式
        reminders = self.to_reminder_format(measures)

        return PreservationExtractionResult(
            success=True,
            measures=measures,
            reminders=reminders,
            model_used=model_used,
            raw_response=llm_response,
        )

    # --- 中文标点 → 半角标点映射（保留日期分隔符"年""月""日"） ---
    _PUNCTUATION_MAP: dict[str, str] = {
        "\uff0c": ",",   # 全角逗号 → 半角逗号
        "\u3002": ".",   # 全角句号 → 半角句号
        "\uff1b": ";",   # 全角分号 → 半角分号
        "\uff1a": ":",   # 全角冒号 → 半角冒号
        "\uff01": "!",   # 全角感叹号 → 半角感叹号
        "\uff1f": "?",   # 全角问号 → 半角问号
        "\u3001": ",",   # 顿号 → 半角逗号
    }

    _MAX_TEXT_LENGTH: int = 8000

    def _preprocess_text(self, text: str) -> str:
        """
        预处理文本，移除乱码、规范化空白，保留日期分隔符

        处理步骤:
        1. 移除 NUL 字符和 Unicode 替换字符
        2. 规范化连续空白为单个空格（保留换行符）
        3. 规范化中文标点（全角→半角，保留"年""月""日"等日期分隔符）
        4. 截取前 8000 字符，超出时记录日志

        Args:
            text: 原始文本

        Returns:
            预处理后的文本

        Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
        """
        # 1. 移除 NUL 字符（\x00）和 Unicode 替换字符（\ufffd）
        cleaned = text.replace("\x00", "").replace("\ufffd", "")

        # 2. 规范化连续空白为单个空格（保留换行符）
        #    先将非换行空白字符的连续序列替换为单个空格
        cleaned = re.sub(r"[^\S\n]+", " ", cleaned)
        #    再将连续换行（含可能夹杂的空格）规范为单个换行
        cleaned = re.sub(r"(\s*\n\s*)+", "\n", cleaned)

        # 3. 规范化中文标点（全角→半角），保留"年""月""日"等日期分隔符
        for full_width, half_width in self._PUNCTUATION_MAP.items():
            cleaned = cleaned.replace(full_width, half_width)

        # 4. strip 首尾空白
        cleaned = cleaned.strip()

        # 5. 截取前 8000 字符，超出时记录日志
        if len(cleaned) > self._MAX_TEXT_LENGTH:
            original_length = len(cleaned)
            cleaned = cleaned[: self._MAX_TEXT_LENGTH]
            logger.info(
                "文本预处理截断: 原始长度 %d, 截断至 %d 字符",
                original_length,
                self._MAX_TEXT_LENGTH,
            )

        return cleaned

    def _call_llm(self, text: str) -> tuple[str, str]:
        """
        调用大模型分析文本

        使用统一 LLM 服务,自动处理后端选择和降级

        Args:
            text: 文书文本

        Returns:
            (大模型返回的字符串, 使用的模型名称)

        Requirements: 6.1, 6.2, 6.4
        """
        from apps.core.services.wiring import get_llm_service

        prompt = PRESERVATION_DATE_EXTRACTION_PROMPT.format(text=text)

        # 使用统一 LLM 服务,优先 Ollama,自动降级到 SiliconFlow
        llm_service = get_llm_service()
        response = llm_service.complete(
            prompt=prompt,
            backend="ollama",  # 优先使用 Ollama
            temperature=0.1,
            fallback=True,  # 启用降级到 SiliconFlow
        )

        if not response or not response.content:
            raise ValidationException(message=_("大模型调用失败"), code="LLM_ERROR", errors={})

        model_used = f"{response.backend}/{response.model}" if hasattr(response, "backend") else response.model
        logger.info(f"使用模型: {model_used}")
        return response.content, model_used

    def _parse_llm_response(self, response: str) -> list[PreservationMeasure]:
        """
        解析大模型返回的 JSON

        支持两种格式:
        1. {"measures": [...]} - 标准格式
        2. [...] - 直接数组格式(小模型可能返回)

        Args:
            response: 大模型返回的字符串

        Returns:
            保全措施列表
        """
        # 尝试从响应中提取 JSON
        json_str = self._extract_json(response)
        if not json_str:
            # 记录详细的原始响应用于调试
            logger.error(f"无法从响应中提取有效 JSON,原始响应长度: {len(response)}, 内容: {response}")
            raise ValueError(f"无法从响应中提取有效 JSON,模型返回内容可能被截断.原始响应: {response[:200]}...")

        data = json.loads(json_str)

        # 兼容两种格式:{"measures": [...]} 或直接 [...]
        if isinstance(data, list):
            measures_data = data
        elif isinstance(data, dict):
            measures_data = data.get("measures", [])
        else:
            measures_data = []

        if not measures_data:
            return []

        measures: list[Any] = []
        for item in measures_data:
            measure = self._parse_measure_item(item)
            if measure:
                measures.append(measure)

        return measures

    def _extract_json(self, text: str) -> str | None:
        """
        从文本中提取 JSON 字符串

        支持以下格式:
        1. ```json ... ```（多代码块时选取包含 "measures" 的块）
        2. { ... }
        3. [ ... ] (数组格式)
        4. 标准解析失败后尝试 _fix_json 修复

        Args:
            text: 原始文本

        Returns:
            JSON 字符串,未找到返回 None

        Requirements: 3.4, 3.5, 3.6
        """
        # 1. 空字符串/空白检查 → 返回 None（Requirements 3.6）
        if not text or not text.strip():
            return None

        # 2. 尝试匹配 ```json ... ```，支持多代码块（Requirements 3.4）
        json_block_pattern = r"```json\s*([\s\S]*?)\s*```"
        blocks: list[str] = re.findall(json_block_pattern, text)
        if blocks:
            # 多代码块场景：优先选取包含 "measures" 键的代码块
            if len(blocks) > 1:
                for block in blocks:
                    stripped = block.strip()
                    if '"measures"' in stripped and self._is_valid_json(stripped):
                        return stripped
            # 单代码块或未找到含 measures 的块，使用第一个有效块
            for block in blocks:
                stripped = block.strip()
                if self._is_valid_json(stripped):
                    return stripped

        # 3. 尝试匹配完整的 JSON 对象(从 { 到最后一个 })
        brace_pattern = r"\{[\s\S]*\}"
        match = re.search(brace_pattern, text)
        if match:
            json_str = match.group(0).strip()
            if self._is_valid_json(json_str):
                return json_str

        # 4. 尝试匹配 JSON 数组(从 [ 到最后一个 ])
        bracket_pattern = r"\[[\s\S]*\]"
        match = re.search(bracket_pattern, text)
        if match:
            json_str = match.group(0).strip()
            if self._is_valid_json(json_str):
                return json_str

        # 5. 标准解析失败，尝试 _fix_json 修复流程（Requirements 3.5）
        #    对所有候选 JSON 片段尝试修复
        candidates: list[str] = []
        # 收集代码块候选
        candidates.extend(block.strip() for block in blocks)
        # 收集 {} 候选
        brace_match = re.search(brace_pattern, text)
        if brace_match:
            candidates.append(brace_match.group(0).strip())
        # 收集 [] 候选
        bracket_match = re.search(bracket_pattern, text)
        if bracket_match:
            candidates.append(bracket_match.group(0).strip())

        for candidate in candidates:
            fixed = self._fix_json(candidate)
            if self._is_valid_json(fixed):
                return fixed

        # 6. 所有尝试均失败，记录详细日志（Requirements 3.5）
        logger.warning(
            "JSON 提取失败，所有解析和修复尝试均未成功。"
            "原始响应前500字符: %s",
            text[:500],
        )
        return None

    def _fix_json(self, json_str: str) -> str:
        """
        尝试修复常见的 JSON 格式问题

        修复策略:
        - 移除尾随逗号（,] 和 ,}）
        - 替换单引号为双引号（保留字符串内容中的撇号）

        Args:
            json_str: 待修复的 JSON 字符串

        Returns:
            修复后的 JSON 字符串

        Requirements: 3.1, 3.2, 3.3
        """
        # 1. 移除尾随逗号：,] 和 ,}（Requirements 3.1）
        fixed = re.sub(r",\s*([}\]])", r"\1", json_str)

        # 2. 替换单引号为双引号（Requirements 3.2, 3.3）
        #    使用状态机遍历，区分 JSON 结构引号与字符串内容中的撇号
        #    规则：在双引号字符串内部的单引号（撇号）保留不动，
        #          仅替换作为 JSON 键/值定界符的单引号
        fixed = self._replace_single_quotes(fixed)

        return fixed

    @staticmethod
    def _replace_single_quotes(text: str) -> str:
        """
        将 JSON 中作为定界符的单引号替换为双引号，保留字符串内容中的撇号

        使用状态机逐字符扫描：
        - 遇到未转义的单引号且不在双引号字符串内 → 替换为双引号
        - 在双引号字符串内的所有字符保持不变

        Args:
            text: 待处理的字符串

        Returns:
            替换后的字符串
        """
        result: list[str] = []
        in_double_quote = False
        in_single_quote = False
        i = 0
        length = len(text)

        while i < length:
            ch = text[i]

            # 处理转义字符：跳过下一个字符
            if ch == "\\" and i + 1 < length:
                result.append(ch)
                result.append(text[i + 1])
                i += 2
                continue

            if in_double_quote:
                # 在双引号字符串内，遇到双引号则结束
                if ch == '"':
                    in_double_quote = False
                result.append(ch)
            elif in_single_quote:
                # 在单引号字符串内，遇到单引号则结束并替换为双引号
                if ch == "'":
                    in_single_quote = False
                    result.append('"')
                else:
                    result.append(ch)
            else:
                # 不在任何字符串内
                if ch == '"':
                    in_double_quote = True
                    result.append(ch)
                elif ch == "'":
                    in_single_quote = True
                    result.append('"')
                else:
                    result.append(ch)

            i += 1

        return "".join(result)

    def _is_valid_json(self, json_str: str) -> bool:
        """
        验证 JSON 字符串是否完整有效

        Args:
            json_str: JSON 字符串

        Returns:
            是否有效
        """
        try:
            json.loads(json_str)
            return True
        except json.JSONDecodeError:
            return False

    def _parse_measure_item(self, item: dict[str, Any]) -> PreservationMeasure | None:
        """
        解析单个保全措施项

        综合 LLM 返回的 is_pending、measure_type 和 raw_text 判断轮候状态。
        任一条件为 true 即判定为轮候，并修正 measure_type 和清除日期字段。

        Args:
            item: 保全措施字典

        Returns:
            PreservationMeasure 对象,解析失败返回 None

        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        measure_type = item.get("measure_type", "").strip()
        property_description = item.get("property_description", "").strip()

        # 必须有保全类型和财产描述
        if not measure_type or not property_description:
            return None

        # 解析日期
        start_date = self._parse_date(item.get("start_date"))
        end_date = self._parse_date(item.get("end_date"))

        # --- 轮候状态综合判断 ---
        # 1. LLM 返回的 is_pending 字段作为基础
        is_pending: bool = bool(item.get("is_pending", False))
        pending_note: str | None = item.get("pending_note")
        raw_text: str | None = item.get("raw_text")

        # 2. 检查 measure_type 是否包含"轮候"（保留现有 PENDING_KEYWORDS 检查）
        type_has_pending = any(keyword in measure_type for keyword in PENDING_KEYWORDS)

        # 3. 检查 raw_text 是否包含"轮候"
        raw_text_has_pending = bool(raw_text and "轮候" in raw_text)

        # 4. 综合判断：任一条件为 true → is_pending = True
        if type_has_pending or raw_text_has_pending:
            is_pending = True

        # 5. 若 raw_text 含"轮候"但 measure_type 不含 → 修正 measure_type
        #    例如："冻结" → "轮候冻结"，"查封" → "轮候查封"
        if raw_text_has_pending and "轮候" not in measure_type:
            measure_type = self._fix_pending_measure_type(measure_type)

        # 6. measure_type 含"轮候"但 is_pending=False → 修正为 True（Requirements 5.3）
        if "轮候" in measure_type and not is_pending:
            is_pending = True

        # 7. 轮候措施：duration/start_date/end_date 设为 None，填入默认说明（Requirements 5.4）
        duration: str | None = item.get("duration")
        if is_pending:
            duration = None
            start_date = None
            end_date = None
            if not pending_note:
                pending_note = DEFAULT_PENDING_NOTE

        return PreservationMeasure(
            measure_type=measure_type,
            property_description=property_description,
            duration=duration,
            start_date=start_date,
            end_date=end_date,
            is_pending=is_pending,
            pending_note=pending_note,
            raw_text=raw_text,
        )

    @staticmethod
    def _fix_pending_measure_type(measure_type: str) -> str:
        """
        修正 measure_type 为对应的轮候类型

        当 raw_text 含"轮候"但 measure_type 不含时，在基础措施类型前加"轮候"前缀。
        例如："冻结" → "轮候冻结"，"查封" → "轮候查封"

        Args:
            measure_type: 原始措施类型

        Returns:
            修正后的措施类型
        """
        # 已知的基础措施类型 → 轮候类型映射
        base_type_map: dict[str, str] = {
            "冻结": "轮候冻结",
            "查封": "轮候查封",
        }
        for base_type, pending_type in base_type_map.items():
            if base_type in measure_type:
                return measure_type.replace(base_type, pending_type)
        # 未匹配到已知类型，直接加"轮候"前缀
        return f"轮候{measure_type}"

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """
        解析日期字符串

        支持格式:
        - YYYY-MM-DD（含省略前导零，如 2025-3-5）
        - YYYY年MM月DD日（含省略前导零，如 2025年3月5日）
        - YYYY/MM/DD（含省略前导零）
        - YYYY.MM.DD（含省略前导零）
        - 回退：正则提取数字

        Args:
            date_str: 日期字符串

        Returns:
            datetime 对象,解析失败返回 None

        Requirements: 2.1, 2.2, 2.4, 2.5, 2.6
        """
        if not date_str or date_str == "null":
            return None

        # strip + 移除多余空格（Requirements 2.5）
        date_str = date_str.strip()
        date_str = re.sub(r"\s+", "", date_str)

        # 支持的 strptime 格式列表（%m/%d 已支持省略前导零）
        # Requirements: 2.1 (YYYY/MM/DD), 2.2 (YYYY.MM.DD), 2.4 (省略前导零)
        formats: list[str] = [
            "%Y-%m-%d",
            "%Y年%m月%d日",
            "%Y/%m/%d",
            "%Y.%m.%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # 尝试中文大写数字日期（Requirements 2.3）
        chinese_result = self._parse_chinese_date(date_str)
        if chinese_result is not None:
            return chinese_result

        # 回退：正则提取数字
        numbers: list[str] = re.findall(r"\d+", date_str)
        if len(numbers) >= 3:
            try:
                year = int(numbers[0])
                month = int(numbers[1])
                day = int(numbers[2])
                return datetime(year, month, day)
            except (ValueError, TypeError):
                pass

        return None

    def _parse_chinese_date(self, date_str: str) -> datetime | None:
        """
        解析中文大写数字日期格式

        支持格式如"二〇二五年三月十五日"

        Args:
            date_str: 日期字符串（已经过 strip 和空格移除）

        Returns:
            datetime 对象，解析失败返回 None

        Requirements: 2.3
        """
        # 中文数字到阿拉伯数字的映射
        cn_digit_map: dict[str, int] = {
            "〇": 0, "零": 0, "一": 1, "二": 2, "三": 3,
            "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
            "九": 9,
        }

        # 匹配中文日期格式：X年X月X日
        pattern = r"(.+)年(.+)月(.+)日"
        match = re.match(pattern, date_str)
        if not match:
            return None

        year_str = match.group(1)
        month_str = match.group(2)
        day_str = match.group(3)

        # 检查是否包含中文数字字符（排除纯阿拉伯数字的情况）
        cn_chars = set(cn_digit_map.keys()) | {"十"}
        has_chinese = any(ch in cn_chars for ch in year_str + month_str + day_str)
        if not has_chinese:
            return None

        try:
            year = self._cn_to_year(year_str, cn_digit_map)
            month = self._cn_to_number(month_str, cn_digit_map)
            day = self._cn_to_number(day_str, cn_digit_map)
            return datetime(year, month, day)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _cn_to_year(year_str: str, cn_digit_map: dict[str, int]) -> int:
        """
        将中文年份逐字转换为阿拉伯数字

        例如：二〇二五 → 2025

        Args:
            year_str: 中文年份字符串
            cn_digit_map: 中文数字映射表

        Returns:
            年份整数

        Raises:
            ValueError: 无法转换时
        """
        digits: list[str] = []
        for ch in year_str:
            if ch in cn_digit_map:
                digits.append(str(cn_digit_map[ch]))
            elif ch.isdigit():
                digits.append(ch)
            else:
                raise ValueError(f"无法识别的年份字符: {ch}")
        if not digits:
            raise ValueError("年份为空")
        return int("".join(digits))

    @staticmethod
    def _cn_to_number(cn_str: str, cn_digit_map: dict[str, int]) -> int:
        """
        将中文数字转换为阿拉伯数字，处理"十"的特殊语义

        例如：十五→15、二十→20、二十五→25、三→3、十→10

        Args:
            cn_str: 中文数字字符串
            cn_digit_map: 中文数字映射表

        Returns:
            整数

        Raises:
            ValueError: 无法转换时
        """
        # 纯阿拉伯数字直接返回
        if cn_str.isdigit():
            return int(cn_str)

        if "十" not in cn_str:
            # 无"十"，逐字转换（如"三"→3）
            digits: list[str] = []
            for ch in cn_str:
                if ch in cn_digit_map:
                    digits.append(str(cn_digit_map[ch]))
                elif ch.isdigit():
                    digits.append(ch)
                else:
                    raise ValueError(f"无法识别的数字字符: {ch}")
            if not digits:
                raise ValueError("数字为空")
            return int("".join(digits))

        # 含"十"的处理
        parts = cn_str.split("十")
        tens_part = parts[0]
        ones_part = parts[1] if len(parts) > 1 else ""

        # 十位
        if not tens_part:
            tens = 1  # "十五" → 十位为 1
        elif tens_part in cn_digit_map:
            tens = cn_digit_map[tens_part]
        elif tens_part.isdigit():
            tens = int(tens_part)
        else:
            raise ValueError(f"无法识别的十位字符: {tens_part}")

        # 个位
        if not ones_part:
            ones = 0  # "二十" → 个位为 0
        elif ones_part in cn_digit_map:
            ones = cn_digit_map[ones_part]
        elif ones_part.isdigit():
            ones = int(ones_part)
        else:
            raise ValueError(f"无法识别的个位字符: {ones_part}")

        return tens * 10 + ones

    def to_reminder_format(self, measures: list[PreservationMeasure]) -> list[ReminderData]:
        """
        将保全措施转换为 Reminder 格式

        只为有明确到期时间的保全措施生成 Reminder

        Args:
            measures: 保全措施列表

        Returns:
            Reminder 格式数据列表

        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
        """
        reminders: list[Any] = []

        for measure in measures:
            # 只为有明确到期时间的保全措施生成 Reminder
            if measure.end_date is None:
                continue

            # 构建提醒内容
            content = self._build_reminder_content(measure)

            # 构建元数据
            metadata = {
                "measure_type": measure.measure_type,
                "property_description": measure.property_description,
                "is_pending": measure.is_pending,
            }

            if measure.duration:
                metadata["duration"] = measure.duration
            if measure.start_date:
                metadata["start_date"] = measure.start_date.strftime("%Y-%m-%d")
            if measure.pending_note:
                metadata["pending_note"] = measure.pending_note
            if measure.raw_text:
                metadata["raw_text"] = measure.raw_text

            reminder = ReminderData(
                reminder_type="asset_preservation_expires",
                content=content,
                due_at=measure.end_date,
                metadata=metadata,
            )
            reminders.append(reminder)

        return reminders

    def _build_reminder_content(self, measure: PreservationMeasure) -> str:
        """
        构建提醒内容

        Args:
            measure: 保全措施

        Returns:
            提醒内容字符串
        """
        parts: list[Any] = []
        parts.append(measure.property_description)

        if measure.end_date:
            parts.append(f"到期日:{measure.end_date.strftime('%Y年%m月%d日')}")

        if measure.is_pending:
            parts.append("(轮候状态)")

        return " ".join(parts)

    def extract_from_uploaded_file(
        self,
        file_content_chunks: Any,
        file_name: str,
    ) -> PreservationExtractionResult:
        """从上传的文件中提取财产保全日期.

        处理文件保存、提取和清理的完整流程.

        Args:
            file_content_chunks: 文件内容的 chunks 迭代器
            file_name: 原始文件名

        Returns:
            PreservationExtractionResult: 提取结果
        """
        import uuid

        from django.conf import settings

        from apps.core.filesystem import FolderPathValidator
        from apps.core.utils.path import Path

        temp_dir = Path(str(settings.MEDIA_ROOT)) / "preservation_date" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        batch_id = uuid.uuid4().hex[:8]
        validator = FolderPathValidator()

        try:
            original_name: str = validator.sanitize_file_name(file_name)
        except Exception:
            logger.exception("文件名不合法")
            return PreservationExtractionResult(
                success=False,
                error="文件名不合法",
                extraction_method="",
            )

        safe_name = f"{batch_id}_{uuid.uuid4().hex[:8]}_{original_name}"
        temp_path = temp_dir / safe_name
        validator.ensure_within_base(temp_dir, temp_path)

        logger.info("开始处理财产保全日期提取请求", extra={})

        try:
            with open(str(temp_path), "wb") as f:
                for chunk in file_content_chunks:
                    f.write(chunk)

            return self.extract_from_file(str(temp_path))
        except Exception as e:
            logger.warning("文件处理失败", extra={})
            return PreservationExtractionResult(
                success=False,
                error=f"文件处理失败: {e!s}",
                extraction_method="",
            )
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                logger.warning("清理临时文件失败", extra={})
