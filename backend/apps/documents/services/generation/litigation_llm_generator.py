"""Business logic services."""

import logging
from typing import Any

from pydantic import ValidationError

from apps.core.exceptions import ValidationException

from .outputs import ComplaintOutput, DefenseOutput
from .prompts import PromptTemplateFactory

logger = logging.getLogger("apps.documents.generation")


class LitigationLLMGenerator:
    def __init__(self, llm_service: object | None = None, prompt_factory: PromptTemplateFactory | None = None) -> None:
        self._llm_service = llm_service
        self._prompt_factory = prompt_factory or PromptTemplateFactory()

    @property
    def llm_service(self) -> Any:
        if self._llm_service is None:
            from apps.documents.services.wiring import get_llm_service

            self._llm_service = get_llm_service()
        return self._llm_service

    def generate_complaint(self, case_data: dict[str, Any]) -> Any:
        try:
            prompt = self._prompt_factory.get_complaint_prompt()
            structured_llm = self.llm_service.get_structured_llm(ComplaintOutput, method="json_mode")
            chain = (prompt | structured_llm).with_retry(stop_after_attempt=3, wait_exponential_jitter=True)
            logger.info("开始生成起诉状", extra={"case_data_keys": list[Any](case_data.keys())})
            result = chain.invoke(case_data)
            logger.info("起诉状生成成功")
            return result
        except ValidationError as e:
            logger.error(
                "起诉状结构验证失败",
                extra={"error": str(e), "error_type": "ValidationError"},
                exc_info=True,
            )
            raise ValidationException(
                message=f"起诉状结构验证失败:{e!s}",
                code="COMPLAINT_VALIDATION_FAILED",
                errors={"detail": str(e)},
            ) from e
        except Exception as e:
            logger.error("起诉状生成失败", extra={"error": str(e), "error_type": type(e).__name__}, exc_info=True)
            if isinstance(e, ValidationException):
                raise
            raise ValidationException(
                message=f"起诉状生成失败:{e!s}",
                code="COMPLAINT_GENERATION_FAILED",
                errors={"detail": str(e)},
            ) from e

    def generate_defense(self, case_data: dict[str, Any]) -> Any:
        try:
            prompt = self._prompt_factory.get_defense_prompt()
            structured_llm = self.llm_service.get_structured_llm(DefenseOutput, method="json_mode")
            chain = (prompt | structured_llm).with_retry(stop_after_attempt=3, wait_exponential_jitter=True)
            logger.info("开始生成答辩状", extra={"case_data_keys": list[Any](case_data.keys())})
            result = chain.invoke(case_data)
            logger.info("答辩状生成成功")
            return result
        except ValidationError as e:
            logger.error(
                "答辩状结构验证失败",
                extra={"error": str(e), "error_type": "ValidationError"},
                exc_info=True,
            )
            raise ValidationException(
                message=f"答辩状结构验证失败:{e!s}",
                code="DEFENSE_VALIDATION_FAILED",
                errors={"detail": str(e)},
            ) from e
        except Exception as e:
            logger.error("答辩状生成失败", extra={"error": str(e), "error_type": type(e).__name__}, exc_info=True)
            if isinstance(e, ValidationException):
                raise
            raise ValidationException(
                message=f"答辩状生成失败:{e!s}",
                code="DEFENSE_GENERATION_FAILED",
                errors={"detail": str(e)},
            ) from e
