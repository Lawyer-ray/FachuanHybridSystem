"""受控输出:结构化解析/校验与面向模型的重试原语单元测试。"""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel, Field

from apps.core.llm.structured_output import (
    StructuredValidationError,
    aretry_structured,
    parse_model_content,
    retry_structured,
)


class _Demo(BaseModel):
    name: str = Field(description="名字")
    kind: Literal["a", "b"] = Field(description="类型")


class TestStructuredValidationError:
    def test_is_valueerror_subclass(self):
        err = StructuredValidationError("boom", raw_text="x")
        assert isinstance(err, ValueError)  # 兼容既有 except ValueError 调用方

    def test_feedback_message_with_errors(self):
        err = StructuredValidationError(
            "invalid",
            raw_text='{"name": 1}',
            errors=[{"loc": ("name",), "msg": "Input should be a valid string"}],
        )
        msg = err.feedback_message
        assert "name" in msg
        assert "Input should be a valid string" in msg
        assert '{"name"' in msg  # 原始片段被回注

    def test_feedback_message_with_error_map(self):
        err = StructuredValidationError("no json", raw_text="hello", error_map={"parse": "no valid JSON"})
        assert "no valid JSON" in err.feedback_message


class TestParseModelContent:
    def test_valid(self):
        model = parse_model_content('{"name": "x", "kind": "a"}', _Demo)
        assert model.name == "x"

    def test_invalid_json_raises_structured(self):
        with pytest.raises(StructuredValidationError) as exc:
            parse_model_content("not json at all", _Demo)
        assert exc.value.error_map["parse"]

    def test_schema_violation_carries_errors(self):
        with pytest.raises(StructuredValidationError) as exc:
            parse_model_content('{"name": 1, "kind": "a"}', _Demo)
        assert exc.value.errors
        assert any(error["loc"][0] == "name" for error in exc.value.errors)


class TestRetryStructured:
    def test_retry_succeeds_and_feeds_error_back(self):
        calls = []

        def responder(last_err):
            calls.append(None if last_err is None else last_err.feedback_message)
            if last_err is not None:
                return '{"name": "fixed", "kind": "a"}'
            return "garbage"

        model = retry_structured(model_cls=_Demo, responder=responder, max_attempts=2)
        assert model.name == "fixed"
        assert len(calls) == 2
        assert calls[0] is None
        assert "上次输出未通过校验" in calls[1]

    def test_retry_exhausted_raises(self):
        def responder(last_err):
            return "still garbage"

        with pytest.raises(StructuredValidationError):
            retry_structured(model_cls=_Demo, responder=responder, max_attempts=3)

    def test_max_attempts_validation(self):
        def responder(last_err):
            return "x"

        with pytest.raises(ValueError):
            retry_structured(model_cls=_Demo, responder=responder, max_attempts=0)

    @pytest.mark.asyncio
    async def test_aretry_structured(self):
        async def responder(last_err):
            if last_err is not None:
                return '{"name": "ok", "kind": "b"}'
            return "???"

        model = await aretry_structured(model_cls=_Demo, responder=responder, max_attempts=2)
        assert model.name == "ok"
        assert model.kind == "b"
