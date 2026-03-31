"""
案号提取服务

负责从法院文书中提取案号并同步到案件。
从 CourtSMSService 中解耦出来的独立服务。
"""

import logging
import re
from typing import TYPE_CHECKING, Any

from apps.core.interfaces import ServiceLocator
from apps.core.llm.config import LLMConfig
from apps.core.llm.exceptions import LLMError

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseNumberService, ICaseService, IDocumentProcessingService

logger = logging.getLogger("apps.automation")


class CaseNumberExtractorService:
    """
    案号提取服务

    职责：
    1. 从文书中提取案号（使用 Ollama AI）
    2. 验证和规范化案号
    3. 同步案号到案件

    支持依赖注入，遵循项目架构规范。
    """

    def __init__(
        self,
        document_processing_service: "IDocumentProcessingService | None" = None,
        case_service: "ICaseService | None" = None,
        case_number_service: "ICaseNumberService | None" = None,
        extraction_provider: Any | None = None,
        llm_service: Any | None = None,
    ):
        """
        初始化服务，支持依赖注入

        Args:
            document_processing_service: 文档处理服务（可选）
            case_service: 案件服务（可选）
            case_number_service: 案号服务（可选）
            extraction_provider: 案号提取提供者（可选），需实现 extract(content: str) -> str
        """
        self._document_processing_service = document_processing_service
        self._case_service = case_service
        self._case_number_service = case_number_service
        self._extraction_provider = extraction_provider
        self._llm_service = llm_service

    @property
    def document_processing_service(self) -> "IDocumentProcessingService":
        """延迟加载文档处理服务"""
        if self._document_processing_service is None:
            from apps.core.dependencies.automation_sms_wiring import build_sms_document_processing_service

            self._document_processing_service = build_sms_document_processing_service()
        return self._document_processing_service

    @property
    def case_service(self) -> "ICaseService":
        """延迟加载案件服务"""
        if self._case_service is None:
            from apps.core.dependencies.automation_sms_wiring import build_sms_case_service

            self._case_service = build_sms_case_service()
        return self._case_service

    @property
    def case_number_service(self) -> "ICaseNumberService":
        """延迟加载案号服务"""
        if self._case_number_service is None:
            from apps.core.dependencies.automation_sms_wiring import build_sms_case_number_service

            self._case_number_service = build_sms_case_number_service()
        return self._case_number_service

    @property
    def llm_service(self) -> Any:
        if self._llm_service is None:
            self._llm_service = ServiceLocator.get_llm_service()
        return self._llm_service

    def extract_from_document(self, document_path: str) -> list[str]:
        """
        从文书中提取案号（使用 Ollama AI）

        Args:
            document_path: 文书文件路径

        Returns:
            案号列表（已规范化、去重）
        """
        if not document_path:
            logger.warning("文书路径为空，无法提取案号")
            return []

        try:
            # 读取 PDF 内容
            logger.info(f"开始从文书提取内容: {document_path}")
            result = self.document_processing_service.extract_document_content_by_path_internal(  # type: ignore
                document_path,
                limit=3000,  # 限制字符数以提高处理效率
            )

            if not result or not result.get("text"):
                logger.warning(f"无法从文书中提取文本内容: {document_path}")
                return []

            content = result["text"].strip()
            if not content:
                logger.warning(f"文书内容为空: {document_path}")
                return []

            # 删除空格（PDF 提取的内容可能包含多余空格，影响 Ollama 识别）
            original_len = len(content)
            content = content.replace(" ", "").replace("\u3000", "")  # 删除半角和全角空格
            logger.info(f"从文书中提取到 {original_len} 字符的内容，删除空格后为 {len(content)} 字符")

            # 使用 Ollama 提取案号
            extracted_numbers = self.extract_from_content(content)

            if extracted_numbers:
                logger.info(f"从文书成功提取案号: {document_path}, 案号: {extracted_numbers}")
            else:
                logger.warning(f"从文书未提取到案号: {document_path}")
                # 记录文书内容的前500字符用于调试
                logger.debug(f"文书内容预览（前500字符）: {content[:500]}")

            return extracted_numbers

        except (ConnectionError, LLMError) as e:
            logger.error(f"Ollama 服务不可用，无法从文书提取案号: {document_path}, 错误: {e!s}")
            return []
        except FileNotFoundError as e:
            logger.error(f"文书文件不存在: {document_path}, 错误: {e!s}")
            return []
        except Exception as e:
            logger.error(f"从文书提取案号失败: {document_path}, 错误: {e!s}")
            return []

    def extract_from_content(self, content: str) -> list[str]:
        """
        从文本内容中提取案号（使用 extraction_provider 或 Ollama AI）
        """
        if not content or not content.strip():
            logger.warning("文书内容为空，无法提取案号")
            return []

        # 优先使用注入的 extraction_provider
        if self._extraction_provider is not None:
            try:
                response_text = self._extraction_provider.extract(content=content)
                return self._parse_ollama_response(response_text)
            except Exception as e:
                logger.error(f"extraction_provider 提取案号失败: {e!s}")
                return []

        try:
            prompt = self._build_extract_prompt(content)
            logger.info("开始调用 Ollama 提取案号")
            model = LLMConfig.get_ollama_model()
            llm_response = self.llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                backend="ollama",
                model=model,
                fallback=False,
            )
            content_text = (llm_response.content or "").strip()
            if not content_text:
                logger.warning("Ollama 返回空响应")
                return []

            logger.info(f"Ollama 案号提取响应: {content_text}")

            return self._parse_ollama_response(content_text)

        except LLMError as e:
            logger.error(f"Ollama 服务不可用: {e!s}")
            return []
        except Exception as e:
            logger.error(f"使用 Ollama 提取案号失败: {e!s}")
            return []

    def _build_extract_prompt(self, content: str) -> str:
        """构建案号提取提示词"""
        return f"""
请从以下法律文书内容中提取所有案号。

案号格式规则：
1. 标准格式：(年份)法院代码案件类型序号，如：(2024)粤0604民初12345号
2. 简化格式：法院代码案件类型序号，如：粤0604民初12345号
3. 可能包含全角字符，需要识别
4. 案号通常出现在文书开头或标题中

返回 JSON 格式：{{"case_numbers": ["案号1", "案号2"]}}
如果没有找到案号，返回：{{"case_numbers": []}}

文书内容：
{content}
"""

    def _parse_ollama_response(self, content_text: str) -> list[str]:
        """解析 Ollama 响应，提取案号列表"""
        import json

        try:
            start_idx = content_text.find("{")
            end_idx = content_text.rfind("}") + 1

            if start_idx >= 0 and end_idx > start_idx:
                result = json.loads(content_text[start_idx:end_idx])
                if isinstance(result, dict) and isinstance(result.get("case_numbers"), list):
                    validated = self.validate_and_normalize(result["case_numbers"])
                    logger.info(f"Ollama {'成功提取' if validated else '未提取到有效'}案号: {validated}")
                    return validated

            logger.warning(f"Ollama 返回格式不正确，尝试降级方案: {content_text[:100]}...")
            return self._extract_fallback(content_text)

        except json.JSONDecodeError as e:
            logger.warning(f"解析 Ollama JSON 响应失败，尝试降级方案: {e!s}")
            return self._extract_fallback(content_text)

    def validate_and_normalize(self, case_numbers: list[str]) -> list[str]:
        """验证案号格式有效性并规范化"""
        if not case_numbers:
            logger.debug("案号列表为空，无需验证")
            return []

        try:
            case_number_svc = self.case_number_service
            logger.info(f"开始验证 {len(case_numbers)} 个案号")
            valid_numbers: list[str] = []
            seen: set[str] = set()

            for i, case_number in enumerate(case_numbers):
                normalized = self._normalize_single(case_number, i, case_number_svc)
                if normalized and normalized not in seen:
                    valid_numbers.append(normalized)
                    seen.add(normalized)
                elif normalized:
                    logger.debug(f"案号重复，跳过: {normalized}")

            logger.info(f"案号验证完成: 输入 {len(case_numbers)} 个，有效 {len(valid_numbers)} 个")
            return valid_numbers

        except Exception as e:
            logger.error(f"案号验证和规范化失败: {e!s}")
            return []

    def _normalize_single(self, case_number: str, idx: int, case_number_svc: Any) -> str | None:
        """规范化单个案号，返回规范化结果或 None"""
        standard_pattern = r"^\（\d{4}\）[^）]*?\w+\d+[^0-9]*?\d+号$"
        simple_pattern = r"^[^（）]*?\w+\d+[^0-9]*?\d+号$"

        try:
            if not case_number or not isinstance(case_number, str):
                logger.warning(f"案号 {idx + 1} 无效（空值或非字符串）: {case_number}")
                return None

            original = case_number.strip()
            if not original:
                return None

            try:
                normalized = case_number_svc.normalize_case_number(original)
            except Exception as e:
                logger.warning(f"案号规范化失败: {original}, 错误: {e!s}")
                return None

            if not normalized:
                logger.warning(f"案号规范化后为空，跳过: {original}")
                return None

            try:
                is_valid = re.match(standard_pattern, normalized) or re.match(simple_pattern, normalized)
            except re.error as e:
                logger.warning(f"案号格式验证失败: {normalized}, 正则错误: {e!s}")
                return None

            if is_valid:
                logger.debug(f"案号验证通过: {original} -> {normalized}")
                return normalized  # type: ignore
            else:
                logger.warning(f"案号格式不正确，跳过: {original} -> {normalized}")
                return None

        except Exception as e:
            logger.warning(f"处理案号 {idx + 1} 时发生错误: {case_number}, 错误: {e!s}")
            return None

    def sync_to_case(self, case_id: int, case_numbers: list[str], sms_id: int) -> int:
        """同步案号到案件，检查案件中是否已存在该案号，不存在则写入。"""
        if not case_id:
            logger.warning("案件 ID 为空，无法同步案号")
            return 0

        if not case_numbers:
            logger.info(f"没有案号需要同步: Case ID={case_id}")
            return 0

        try:
            case_number_svc = self.case_number_service
            case_numbers_to_sync = self._deduplicate(case_numbers)
            if not case_numbers_to_sync:
                logger.info(f"去重后没有案号需要同步: Case ID={case_id}")
                return 0

            existing_numbers = self._get_existing_numbers(case_id, case_number_svc)
            if existing_numbers is None:
                return 0

            success_count = self._write_new_numbers(
                case_id, case_numbers_to_sync, existing_numbers, sms_id, case_number_svc
            )

            logger.info(
                f"案号同步完成: SMS ID={sms_id}, {'成功写入' if success_count else '无新案号需要写入'}"
                + (f" {success_count} 个案号" if success_count else "")
            )
            return success_count

        except Exception as e:
            logger.error(f"同步案号失败: Case ID={case_id}, SMS ID={sms_id}, 错误: {e!s}")
            return 0

    def _get_existing_numbers(self, case_id: int, case_number_svc: Any) -> set[str] | None:
        """获取案件现有的规范化案号集合"""
        try:
            existing_case_numbers = self.case_service.get_case_numbers_by_case_internal(case_id)
            result: set[str] = set()
            for cn in existing_case_numbers:
                normalized = case_number_svc.normalize_case_number(cn)
                if normalized:
                    result.add(normalized)
            logger.info(f"案件现有案号数量: {len(result)}, Case ID={case_id}")
            return result
        except Exception as e:
            logger.error(f"获取案件现有案号失败: Case ID={case_id}, 错误: {e!s}")
            return None

    def _write_new_numbers(
        self,
        case_id: int,
        case_numbers: list[str],
        existing: set[str],
        sms_id: int,
        case_number_svc: Any,
    ) -> int:
        """将不存在的案号写入案件，返回成功数量"""
        success_count = 0

        for case_number in case_numbers:
            normalized = case_number_svc.normalize_case_number(case_number)
            if not normalized:
                logger.warning(f"案号格式不正确，跳过: {case_number}")
                continue

            if normalized in existing:
                logger.info(f"案号已存在，跳过: Case ID={case_id}, 案号={normalized}")
                continue

            try:
                case_number_svc.create_number(
                    case_id=case_id,
                    number=normalized,
                    remarks=f"从法院短信自动提取 (SMS ID: {sms_id})",
                )
                logger.info(f"案号写入成功: Case ID={case_id}, 案号={normalized}")
                existing.add(normalized)
                success_count += 1
            except Exception as e:
                logger.error(f"案号写入失败: Case ID={case_id}, 案号={normalized}, 错误: {e!s}")

        return success_count

    def _extract_fallback(self, response_text: str) -> list[str]:
        """
        降级方案：使用正则从响应中提取案号
        """
        if not response_text or not response_text.strip():
            logger.warning("降级方案：响应文本为空")
            return []

        try:
            logger.info("使用降级方案从响应中提取案号")
            found_numbers = self._regex_extract_numbers(response_text)

            if found_numbers:
                logger.info(f"降级方案原始提取结果: {found_numbers}")
            else:
                logger.warning("降级方案未匹配到任何案号模式")

            validated = self.validate_and_normalize(found_numbers)
            logger.info(f"降级方案{'成功提取' if validated else '未能提取到有效'}案号: {validated}")
            return validated

        except Exception as e:
            logger.error(f"降级方案提取案号失败: {e!s}")
            return []

    def _regex_extract_numbers(self, text: str) -> list[str]:
        """使用正则从文本中提取候选案号"""
        patterns = [
            r"\((\d{4})\)([^)]*?\w+\d+[^0-9]*?\d+号)",
            r"([^()\s]*?[0-9]+[^0-9]*?[0-9]+号)",
            r"(\w*\d+\w*\d+号)",
        ]
        found: list[str] = []
        for i, pattern in enumerate(patterns):
            try:
                for match in re.findall(pattern, text):
                    if isinstance(match, tuple):
                        case_number = f"({match[0]}){match[1]}" if len(match) == 2 else match[0]
                    else:
                        case_number = match
                    if case_number and case_number.strip():
                        found.append(case_number.strip())
                logger.debug(f"正则模式 {i + 1} 匹配到 {len(found)} 个结果")
            except re.error as e:
                logger.warning(f"正则模式 {i + 1} 执行失败: {e!s}")
        return found

    def _deduplicate(self, case_numbers: list[str]) -> list[str]:
        """去重处理案号列表"""
        if not case_numbers:
            return []

        try:
            case_number_svc = self.case_number_service
            seen: set[str] = set()
            unique_numbers: list[str] = []

            for case_number in case_numbers:
                if not case_number or not isinstance(case_number, str):
                    continue
                normalized = case_number_svc.normalize_case_number(case_number.strip())
                if normalized and normalized not in seen:
                    unique_numbers.append(normalized)
                    seen.add(normalized)

            logger.debug(f"案号去重完成: 输入 {len(case_numbers)} 个，去重后 {len(unique_numbers)} 个")
            return unique_numbers

        except Exception as e:
            logger.error(f"案号去重失败: {e!s}")
            return case_numbers
