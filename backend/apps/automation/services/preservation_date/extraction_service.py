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

if TYPE_CHECKING:
    from apps.document_recognition.services import TextExtractionService

logger = logging.getLogger("apps.automation.preservation_date")


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

        # 转换为 Reminder 格式
        reminders = self.to_reminder_format(measures)

        return PreservationExtractionResult(
            success=True,
            measures=measures,
            reminders=reminders,
            model_used=model_used,
            raw_response=llm_response,
        )

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
        from apps.automation.services.wiring import get_llm_service

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

    def _extract_json(self, text: str) -> str | None | None:
        """
        从文本中提取 JSON 字符串

        支持以下格式:
        1. ```json ... ```
        2. { ... }
        3. [ ... ] (数组格式)

        Args:
            text: 原始文本

        Returns:
            JSON 字符串,未找到返回 None
        """
        # 尝试匹配 ```json ... ```
        json_block_pattern = r"```json\s*([\s\S]*?)\s*```"
        match = re.search(json_block_pattern, text)
        if match:
            json_str = match.group(1).strip()
            if self._is_valid_json(json_str):
                return json_str

        # 尝试匹配完整的 JSON 对象(从 { 到最后一个 })
        brace_pattern = r"\{[\s\S]*\}"
        match = re.search(brace_pattern, text)
        if match:
            json_str = match.group(0).strip()
            if self._is_valid_json(json_str):
                return json_str

        # 尝试匹配 JSON 数组(从 [ 到最后一个 ])
        bracket_pattern = r"\[[\s\S]*\]"
        match = re.search(bracket_pattern, text)
        if match:
            json_str = match.group(0).strip()
            if self._is_valid_json(json_str):
                return json_str

        return None

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

    def _parse_measure_item(self, item: dict[str, Any]) -> PreservationMeasure | None | None:
        """
        解析单个保全措施项

        Args:
            item: 保全措施字典

        Returns:
            PreservationMeasure 对象,解析失败返回 None
        """
        measure_type = item.get("measure_type", "").strip()
        property_description = item.get("property_description", "").strip()

        # 必须有保全类型和财产描述
        if not measure_type or not property_description:
            return None

        # 解析日期
        start_date = self._parse_date(item.get("start_date"))
        end_date = self._parse_date(item.get("end_date"))

        # 处理轮候状态
        is_pending = item.get("is_pending", False)
        pending_note = item.get("pending_note")

        # 如果保全类型包含轮候关键词,自动标记为轮候状态
        if any(keyword in measure_type for keyword in PENDING_KEYWORDS):
            is_pending = True
            if not pending_note:
                pending_note = DEFAULT_PENDING_NOTE

        return PreservationMeasure(
            measure_type=measure_type,
            property_description=property_description,
            duration=item.get("duration"),
            start_date=start_date,
            end_date=end_date,
            is_pending=is_pending,
            pending_note=pending_note,
            raw_text=item.get("raw_text"),
        )

    def _parse_date(self, date_str: str | None) -> datetime | None | None:
        """
        解析日期字符串

        支持格式:
        - YYYY-MM-DD
        - YYYY年MM月DD日

        Args:
            date_str: 日期字符串

        Returns:
            datetime 对象,解析失败返回 None
        """
        if not date_str or date_str == "null":
            return None

        date_str = date_str.strip()

        # 尝试 YYYY-MM-DD 格式
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            pass

        # 尝试 YYYY年MM月DD日 格式
        try:
            return datetime.strptime(date_str, "%Y年%m月%d日")
        except ValueError:
            pass

        # 尝试提取数字
        numbers = re.findall(r"\d+", date_str)
        if len(numbers) >= 3:
            try:
                year = int(numbers[0])
                month = int(numbers[1])
                day = int(numbers[2])
                return datetime(year, month, day)
            except (ValueError, TypeError):
                pass

        return None

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
        from apps.core.path import Path

        temp_dir = Path(str(settings.MEDIA_ROOT)) / "automation" / "temp" / "preservation_date"
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
