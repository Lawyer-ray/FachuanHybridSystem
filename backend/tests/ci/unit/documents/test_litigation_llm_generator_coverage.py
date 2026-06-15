"""Tests for litigation_llm_generator — coverage for uncovered branches."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from apps.core.exceptions import ValidationException
from apps.documents.services.generation.litigation_llm_generator import LitigationLLMGenerator


class TestLitigationLLMGeneratorInit:
    def test_default_llm_service(self) -> None:
        gen = LitigationLLMGenerator()
        assert gen._llm_service is None

    def test_injected_llm_service(self) -> None:
        mock_llm = MagicMock()
        gen = LitigationLLMGenerator(llm_service=mock_llm)
        assert gen.llm_service is mock_llm

    def test_lazy_loads_llm_service(self) -> None:
        gen = LitigationLLMGenerator()
        with patch("apps.documents.services.infrastructure.wiring.get_llm_service") as mock_get:
            mock_get.return_value = MagicMock()
            result = gen.llm_service
            assert result is not None


class TestInvokeStructured:
    def test_success_first_attempt(self) -> None:
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"plaintiff": "test"}'
        mock_llm.chat.return_value = mock_response

        gen = LitigationLLMGenerator(llm_service=mock_llm)
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.render_user_message.return_value = "user msg"

        with patch("apps.documents.services.generation.litigation_llm_generator.parse_model_content") as mock_parse:
            mock_parse.return_value = MagicMock()
            result = gen._invoke_structured(
                prompt=prompt,
                case_data={"key": "val"},
                output_model=MagicMock(),
                max_retries=3,
            )
            assert result is not None

    def test_retries_on_exception(self) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [Exception("err1"), Exception("err2"), MagicMock(content='{"plaintiff": "ok"}')]

        gen = LitigationLLMGenerator(llm_service=mock_llm)
        prompt = MagicMock()
        prompt.system_prompt = "sys"
        prompt.render_user_message.return_value = "msg"

        with patch("apps.documents.services.generation.litigation_llm_generator.parse_model_content") as mock_parse:
            mock_parse.return_value = MagicMock()
            result = gen._invoke_structured(
                prompt=prompt,
                case_data={},
                output_model=MagicMock(),
                max_retries=3,
            )
            assert result is not None
            assert mock_llm.chat.call_count == 3

    def test_validation_error_propagates(self) -> None:
        from pydantic import BaseModel

        class Dummy(BaseModel):
            x: int

        mock_llm = MagicMock()

        gen = LitigationLLMGenerator(llm_service=mock_llm)
        prompt = MagicMock()
        prompt.system_prompt = "sys"
        prompt.render_user_message.return_value = "msg"

        # Force a ValidationError from parse_model_content
        try:
            Dummy.model_validate({"x": "not_an_int"})
        except ValidationError as ve:
            validation_err = ve

        with patch("apps.documents.services.generation.litigation_llm_generator.parse_model_content") as mock_parse:
            mock_parse.side_effect = validation_err
            with pytest.raises(ValidationError):
                gen._invoke_structured(
                    prompt=prompt,
                    case_data={},
                    output_model=Dummy,
                    max_retries=1,
                )

    def test_generic_error_propagates_after_retries(self) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = RuntimeError("llm down")

        gen = LitigationLLMGenerator(llm_service=mock_llm)
        prompt = MagicMock()
        prompt.system_prompt = "sys"
        prompt.render_user_message.return_value = "msg"

        with pytest.raises(RuntimeError, match="llm down"):
            gen._invoke_structured(
                prompt=prompt,
                case_data={},
                output_model=MagicMock(),
                max_retries=2,
            )


_VALIDATION_ERROR: ValidationError | None = None


def _get_validation_error() -> ValidationError:
    global _VALIDATION_ERROR  # noqa: PLW0603
    if _VALIDATION_ERROR is None:
        from pydantic import BaseModel

        class Dummy(BaseModel):
            x: int

        try:
            Dummy.model_validate({"x": "not_an_int"})
        except ValidationError as ve:
            _VALIDATION_ERROR = ve
    return _VALIDATION_ERROR  # type: ignore[return-value]


class TestGenerateComplaint:
    def test_success(self) -> None:
        mock_llm = MagicMock()
        gen = LitigationLLMGenerator(llm_service=mock_llm)

        with (
            patch("apps.documents.services.generation.litigation_llm_generator.get_complaint_prompt") as mock_prompt,
            patch.object(gen, "_invoke_structured") as mock_invoke,
        ):
            mock_invoke.return_value = MagicMock()
            result = gen.generate_complaint({"key": "val"})
            assert result is not None

    def test_validation_error_wrapped(self) -> None:
        mock_llm = MagicMock()
        gen = LitigationLLMGenerator(llm_service=mock_llm)

        with (
            patch("apps.documents.services.generation.litigation_llm_generator.get_complaint_prompt"),
            patch.object(gen, "_invoke_structured", side_effect=_get_validation_error()),
        ):
            with pytest.raises(ValidationException, match="起诉状结构验证失败"):
                gen.generate_complaint({"key": "val"})

    def test_generic_error_wrapped(self) -> None:
        mock_llm = MagicMock()
        gen = LitigationLLMGenerator(llm_service=mock_llm)

        with (
            patch("apps.documents.services.generation.litigation_llm_generator.get_complaint_prompt"),
            patch.object(gen, "_invoke_structured", side_effect=RuntimeError("llm failed")),
        ):
            with pytest.raises(ValidationException, match="起诉状生成失败"):
                gen.generate_complaint({"key": "val"})


class TestGenerateDefense:
    def test_success(self) -> None:
        mock_llm = MagicMock()
        gen = LitigationLLMGenerator(llm_service=mock_llm)

        with (
            patch("apps.documents.services.generation.litigation_llm_generator.get_defense_prompt") as mock_prompt,
            patch.object(gen, "_invoke_structured") as mock_invoke,
        ):
            mock_invoke.return_value = MagicMock()
            result = gen.generate_defense({"key": "val"})
            assert result is not None

    def test_validation_error_wrapped(self) -> None:
        mock_llm = MagicMock()
        gen = LitigationLLMGenerator(llm_service=mock_llm)

        with (
            patch("apps.documents.services.generation.litigation_llm_generator.get_defense_prompt"),
            patch.object(gen, "_invoke_structured", side_effect=_get_validation_error()),
        ):
            with pytest.raises(ValidationException, match="答辩状结构验证失败"):
                gen.generate_defense({"key": "val"})

    def test_generic_error_wrapped(self) -> None:
        mock_llm = MagicMock()
        gen = LitigationLLMGenerator(llm_service=mock_llm)

        with (
            patch("apps.documents.services.generation.litigation_llm_generator.get_defense_prompt"),
            patch.object(gen, "_invoke_structured", side_effect=RuntimeError("llm failed")),
        ):
            with pytest.raises(ValidationException, match="答辩状生成失败"):
                gen.generate_defense({"key": "val"})
