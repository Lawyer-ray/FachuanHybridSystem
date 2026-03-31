"""
图片自动重命名服务

从 OCR 文本中提取日期和金额信息,生成标准化文件名.
使用 Ollama 本地模型进行智能提取.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

from apps.core.llm.exceptions import LLMNetworkError, LLMTimeoutError

logger = logging.getLogger("apps.image_rotation")


# LLM 提取 Prompt 模板
EXTRACTION_PROMPT = """
从以下 OCR 识别的文本中提取日期和金额信息.

文本内容:
{ocr_text}

请按以下 JSON 格式返回:
{{
    "date": "8位纯数字日期,格式必须是YYYYMMDD,例如20250630,不要任何分隔符,如果没有则为 null",
    "amount": "金额数字+元,如 65500元,如果没有则为 null",
    "raw_date": "原文中的日期文本,如果没有则为 null",
    "raw_amount": "原文中的金额文本,如果没有则为 null"
}}

注意:
1. date 字段必须是8位纯数字,不能有任何分隔符(-、/、.等),例如:20250630
2. 日期格式可能是:2025年6月30日、2025-06-30、2025/06/30 等,但输出必须转换为 YYYYMMDD
3. 金额格式可能是:65500元、65,500.00元、￥65500、人民币65500元 等
4. 如果有多个日期,选择最显眼或最相关的一个
5. 如果有多个金额,选择最大的或最相关的一个
6. 只返回 JSON,不要其他内容
"""


@dataclass
class ExtractionResult:
    """LLM 提取结果"""

    date: str | None = None  # 标准化日期 YYYYMMDD
    amount: str | None = None  # 标准化金额 如 "65500元"
    raw_date: str | None = None  # 原始日期文本
    raw_amount: str | None = None  # 原始金额文本


@dataclass
class RenameSuggestion:
    """重命名建议"""

    original_filename: str  # 原始文件名
    suggested_filename: str  # 建议的新文件名
    date: str | None = None  # 提取的日期
    amount: str | None = None  # 提取的金额
    success: bool = True  # 是否成功
    error: str | None = None  # 错误信息


class AutoRenameService:
    """自动重命名服务 - 使用 Ollama 本地模型"""

    def __init__(
        self,
        ollama_model: str | None = None,
        ollama_base_url: str | None = None,
        llm_client: Any | None = None,
    ) -> None:
        from apps.core.llm.config import LLMConfig

        self._ollama_model = ollama_model or LLMConfig.get_ollama_model()
        self._ollama_base_url = ollama_base_url or LLMConfig.get_ollama_base_url()
        self._llm_client = llm_client
        self._ocr_channel: Any | None = None

    def extract_info(self, ocr_text: str) -> ExtractionResult:
        """
        从 OCR 文本中提取日期和金额

        使用 LLM 智能提取日期和金额信息,支持多种格式.
        当 LLM 调用失败或 JSON 解析失败时,返回空结果而非抛出异常.

        Args:
            ocr_text: OCR 识别的文本

        Returns:
            ExtractionResult: 包含 date 和 amount 的提取结果

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
        """
        # 空文本直接返回空结果
        if not ocr_text or not ocr_text.strip():
            return ExtractionResult()

        # 构建 prompt
        prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)
        messages: list[Any] = [{"role": "user", "content": prompt}]
        try:
            if self._llm_client is not None:
                llm_resp = self._llm_client.complete(prompt)
                response_text = (llm_resp.content or "").strip()
            else:
                from apps.core.interfaces import ServiceLocator

                llm_service = ServiceLocator.get_llm_service()
                llm_resp = llm_service.chat(
                    messages=messages, backend="ollama", model=self._ollama_model, fallback=False
                )
                response_text = (llm_resp.content or "").strip()
            if not response_text:
                logger.warning("LLM 返回内容为空")
                return ExtractionResult()

        except LLMNetworkError as e:
            logger.warning("Ollama 服务不可用，跳过 LLM 提取: %s", e)
            return ExtractionResult()
        except LLMTimeoutError as e:
            logger.warning("Ollama 请求超时，跳过 LLM 提取: %s", e)
            return ExtractionResult()
        except Exception as e:
            logger.warning("Ollama 调用失败: %s", e)
            return ExtractionResult()

        # 解析 JSON 响应
        return self._parse_extraction_response(response_text)

    def _parse_extraction_response(self, response_text: str) -> ExtractionResult:
        """
        解析 LLM 返回的 JSON 响应

        Args:
            response_text: LLM 返回的文本

        Returns:
            ExtractionResult: 解析后的提取结果
        """
        # 尝试提取 JSON 块(处理 markdown 代码块)
        json_text = self._extract_json_block(response_text)

        # 尝试标准 JSON 解析
        try:
            data = json.loads(json_text)
            date = data.get("date")
            # 标准化日期格式:移除所有非数字字符
            if date:
                date = self._normalize_date(date)
            return ExtractionResult(
                date=date,
                amount=data.get("amount"),
                raw_date=data.get("raw_date"),
                raw_amount=data.get("raw_amount"),
            )
        except json.JSONDecodeError:
            logger.warning(f"JSON 解析失败,尝试正则提取: {response_text[:200]}")
            return self._fallback_regex_extraction(response_text)

    def _normalize_date(self, date_str: str) -> str | None | None:
        """
        标准化日期格式为 YYYYMMDD(8位纯数字)

        移除所有非数字字符,确保输出为8位纯数字格式.

        Args:
            date_str: 原始日期字符串

        Returns:
            标准化后的日期字符串,如果无法标准化则返回 None
        """
        if not date_str:
            return None

        # 移除所有非数字字符
        digits_only = re.sub(r"\D", "", date_str)

        # 验证是否为8位数字
        if len(digits_only) == 8:
            return digits_only

        # 如果是6位数字(YYMMDD),尝试补全年份
        if len(digits_only) == 6:
            year_prefix = "20" if int(digits_only[:2]) < 50 else "19"
            return year_prefix + digits_only

        logger.warning(f"日期格式无法标准化: {date_str} -> {digits_only}")
        return None

    def _extract_json_block(self, text: str) -> str:
        """
        从文本中提取 JSON 块

        处理 LLM 可能返回的 markdown 代码块格式.

        Args:
            text: 原始文本

        Returns:
            提取的 JSON 文本
        """
        # 尝试匹配 ```json ... ``` 或 ``` ... ```
        json_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        match = re.search(json_block_pattern, text)
        if match:
            return match.group(1).strip()

        # 尝试匹配 { ... } 块
        brace_pattern = r"\{[\s\S]*\}"
        match = re.search(brace_pattern, text)
        if match:
            return match.group(0)

        return text

    def _fallback_regex_extraction(self, response_text: str) -> ExtractionResult:
        """
        JSON 解析失败时的降级正则提取

        Args:
            response_text: LLM 返回的文本

        Returns:
            ExtractionResult: 通过正则提取的结果
        """
        date = None
        amount = None
        raw_date = None
        raw_amount = None

        # 尝试提取 date 字段(支持带分隔符的格式)
        date_match = re.search(r'"date"\s*:\s*"([^"]+)"', response_text)
        if date_match and date_match.group(1).lower() != "null":
            date = self._normalize_date(date_match.group(1))

        # 尝试提取 amount 字段
        amount_match = re.search(r'"amount"\s*:\s*"([^"]+元)"', response_text)
        if amount_match:
            amount = amount_match.group(1)

        # 尝试提取 raw_date 字段
        raw_date_match = re.search(r'"raw_date"\s*:\s*"([^"]+)"', response_text)
        if raw_date_match and raw_date_match.group(1).lower() != "null":
            raw_date = raw_date_match.group(1)

        # 尝试提取 raw_amount 字段
        raw_amount_match = re.search(r'"raw_amount"\s*:\s*"([^"]+)"', response_text)
        if raw_amount_match and raw_amount_match.group(1).lower() != "null":
            raw_amount = raw_amount_match.group(1)

        return ExtractionResult(
            date=date,
            amount=amount,
            raw_date=raw_date,
            raw_amount=raw_amount,
        )

    def generate_filename(
        self,
        original_filename: str,
        extraction_result: ExtractionResult,
    ) -> str:
        """
        根据提取结果生成新文件名

        根据提取的日期和金额生成标准化文件名,保留原文件扩展名.

        规则:
        - 同时有日期和金额:日期_金额.扩展名(如 20250630_65500元.jpg)
        - 只有日期:日期.扩展名(如 20250630.jpg)
        - 只有金额:金额.扩展名(如 65500元.jpg)
        - 都没有:保持原文件名不变

        Args:
            original_filename: 原始文件名
            extraction_result: 提取结果

        Returns:
            建议的新文件名

        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
        """
        # 提取原文件扩展名
        extension = self._get_file_extension(original_filename)

        date = extraction_result.date
        amount = extraction_result.amount

        # 根据提取结果生成文件名
        if date and amount:
            # 同时有日期和金额:日期_金额.扩展名
            return f"{date}_{amount}{extension}"
        elif date:
            # 只有日期:日期.扩展名
            return f"{date}{extension}"
        elif amount:
            # 只有金额:金额.扩展名
            return f"{amount}{extension}"
        else:
            # 都没有:保持原文件名
            return original_filename

    def _get_file_extension(self, filename: str) -> str:
        """
        获取文件扩展名(包含点号)

        Args:
            filename: 文件名

        Returns:
            扩展名(如 ".jpg"),无扩展名时返回空字符串
        """
        if "." in filename:
            # 找到最后一个点的位置
            last_dot = filename.rfind(".")
            return filename[last_dot:]
        return ""

    def _get_ocr_channel(self) -> Any | None:
        """延迟初始化 RenameOCRChannel，失败时返回 None"""
        if self._ocr_channel is not None:
            return self._ocr_channel
        try:
            from apps.image_rotation.services.rename_ocr import RenameOCRChannel

            self._ocr_channel = RenameOCRChannel()
            return self._ocr_channel
        except Exception:
            logger.warning("RenameOCRChannel 初始化失败", exc_info=True)
            return None

    def suggest_rename_with_image(
        self,
        original_filename: str,
        ocr_text: str,
        image_data: bytes,
        rotation: int,
    ) -> RenameSuggestion:
        """
        使用高精度 OCR 通道重新识别后生成重命名建议。

        OCR 通道不可用时回退到 ocr_text。

        Requirements: 5.3, 5.4
        """
        enhanced_ocr_text = ocr_text

        channel = self._get_ocr_channel()
        if channel is not None:
            result = channel.recognize(image_data, rotation)
            if result is not None and result.text.strip():
                enhanced_ocr_text = result.text
                logger.info(
                    "使用高精度 OCR 文本替代原始文本: %s (置信度 %.3f)",
                    original_filename,
                    result.overall_confidence,
                )

        return self.suggest_rename(original_filename, enhanced_ocr_text)

    def suggest_rename(self, original_filename: str, ocr_text: str) -> RenameSuggestion:
        """
        获取重命名建议(组合方法)

        组合 extract_info 和 generate_filename 方法,从 OCR 文本中提取信息并生成建议文件名.
        处理异常时返回带有错误信息的 RenameSuggestion,而非抛出异常.

        Args:
            original_filename: 原始文件名
            ocr_text: OCR 识别的文本

        Returns:
            RenameSuggestion: 包含原文件名、建议文件名、提取信息

        Requirements: 4.2, 4.4
        """
        try:
            # 1. 提取日期和金额信息
            extraction_result = self.extract_info(ocr_text)

            # 2. 生成建议文件名
            suggested_filename = self.generate_filename(original_filename, extraction_result)

            # 3. 返回重命名建议
            return RenameSuggestion(
                original_filename=original_filename,
                suggested_filename=suggested_filename,
                date=extraction_result.date,
                amount=extraction_result.amount,
                success=True,
                error=None,
            )
        except Exception as e:
            # 处理异常:返回失败的建议,使用原文件名
            logger.warning(f"重命名建议生成失败: {original_filename}, 错误: {e}")
            return RenameSuggestion(
                original_filename=original_filename,
                suggested_filename=original_filename,
                date=None,
                amount=None,
                success=False,
                error=str(e),
            )

    def suggest_rename_batch(
        self,
        items: list["RenameRequestItem"],
    ) -> list[RenameSuggestion]:
        """
        批量获取重命名建议

        检测请求项是否包含 image_data 和 rotation 属性，
        有图片数据时调用 suggest_rename_with_image()，否则调用原有 suggest_rename()。

        Requirements: 4.2, 4.4, 5.3, 5.4
        """
        suggestions: list[RenameSuggestion] = []

        for item in items:
            image_data: bytes | None = getattr(item, "image_data", None)
            rotation: int = getattr(item, "rotation", 0)

            if image_data:
                suggestion = self.suggest_rename_with_image(
                    item.filename,
                    item.ocr_text,
                    image_data,
                    rotation,
                )
            else:
                suggestion = self.suggest_rename(item.filename, item.ocr_text)
            suggestions.append(suggestion)

        return suggestions


class RenameRequestItem(Protocol):
    filename: str
    ocr_text: str
