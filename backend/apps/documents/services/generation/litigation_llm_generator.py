"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel, ValidationError

from apps.core.exceptions import ValidationException
from apps.core.llm.structured_output import parse_model_content

from .outputs import ComplaintOutput, DefenseOutput
from .prompts import PromptSpec, get_complaint_prompt, get_defense_prompt

logger = logging.getLogger("apps.documents.generation")

TOutput = TypeVar("TOutput", bound=BaseModel)


class LitigationLLMGenerator:
    def __init__(self, llm_service: object | None = None) -> None:
        self._llm_service = llm_service

    @property
    def llm_service(self) -> Any:
        if self._llm_service is None:
            from apps.documents.services.infrastructure.wiring import get_llm_service

            self._llm_service = get_llm_service()
        return self._llm_service

    def _invoke_structured(
        self,
        *,
        prompt: PromptSpec,
        case_data: dict[str, Any],
        output_model: type[TOutput],
        max_retries: int = 3,
    ) -> TOutput:
        messages = [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": prompt.render_user_message(case_data)},
        ]

        last_error: Exception | None = None
        for _attempt in range(max_retries):
            try:
                llm_response = self.llm_service.chat(messages=messages)
                return parse_model_content(llm_response.content, output_model)
            except Exception as exc:
                last_error = exc

        if isinstance(last_error, ValidationError):
            raise last_error

        if last_error is None:
            raise RuntimeError("LLM structured invocation failed without error")
        raise last_error

    def generate_complaint(self, case_data: dict[str, Any]) -> Any:
        try:
            prompt = get_complaint_prompt()
            logger.info("开始生成起诉状", extra={"case_data_keys": list(case_data.keys())})
            result = self._invoke_structured(prompt=prompt, case_data=case_data, output_model=ComplaintOutput)
            logger.info("起诉状生成成功")
            return result
        except ValidationError as e:
            logger.error(
                "起诉状结构验证失败",
                extra={"error": str(e), "error_type": "ValidationError"},
                exc_info=True,
            )
            raise ValidationException(
                message=_("起诉状结构验证失败:%(e)s") % {"e": e},
                code="COMPLAINT_VALIDATION_FAILED",
                errors={"detail": str(e)},
            ) from e
        except Exception as e:
            logger.error("起诉状生成失败", extra={"error": str(e), "error_type": type(e).__name__}, exc_info=True)
            if isinstance(e, ValidationException):
                raise
            raise ValidationException(
                message=_("起诉状生成失败:%(e)s") % {"e": e},
                code="COMPLAINT_GENERATION_FAILED",
                errors={"detail": str(e)},
            ) from e

    def generate_defense(self, case_data: dict[str, Any]) -> Any:
        try:
            prompt = get_defense_prompt()
            logger.info("开始生成答辩状", extra={"case_data_keys": list(case_data.keys())})
            result = self._invoke_structured(prompt=prompt, case_data=case_data, output_model=DefenseOutput)
            logger.info("答辩状生成成功")
            return result
        except ValidationError as e:
            logger.error(
                "答辩状结构验证失败",
                extra={"error": str(e), "error_type": "ValidationError"},
                exc_info=True,
            )
            raise ValidationException(
                message=_("答辩状结构验证失败:%(e)s") % {"e": e},
                code="DEFENSE_VALIDATION_FAILED",
                errors={"detail": str(e)},
            ) from e
        except Exception as e:
            logger.error("答辩状生成失败", extra={"error": str(e), "error_type": type(e).__name__}, exc_info=True)
            if isinstance(e, ValidationException):
                raise
            raise ValidationException(
                message=_("答辩状生成失败:%(e)s") % {"e": e},
                code="DEFENSE_GENERATION_FAILED",
                errors={"detail": str(e)},
            ) from e
