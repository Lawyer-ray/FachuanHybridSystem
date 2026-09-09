"""Helpers for extracting structured JSON output from LLM responses."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ValidationError

TModel = TypeVar("TModel", bound=BaseModel)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


def clean_text(text: str) -> str:
    """Remove common wrappers around model output."""
    cleaned = text or ""
    for marker in [
        "```json",
        "```",
        "<|begin_of_text|>",
        "<|end_of_text|>",
        "<|begin_of_box|>",
        "<|end_of_box|>",
    ]:
        cleaned = cleaned.replace(marker, "")
    return cleaned.strip()


def extract_json_text(text: str) -> str | None:
    """Extract the first valid JSON object/array text from a model response."""
    cleaned = clean_text(text)
    if not cleaned:
        return None

    for candidate in [cleaned, *_CODE_FENCE_RE.findall(cleaned)]:
        snippet = (candidate or "").strip()
        if not snippet:
            continue
        try:
            json.loads(snippet)
            return snippet
        except json.JSONDecodeError:
            pass

    stack: list[str] = []
    start_idx: int | None = None
    for idx, ch in enumerate(cleaned):
        if ch in "[{":
            if not stack:
                start_idx = idx
            stack.append(ch)
            continue

        if ch not in "]}":
            continue

        if not stack:
            continue

        opening = stack.pop()
        if (opening == "{" and ch != "}") or (opening == "[" and ch != "]"):
            stack = []
            start_idx = None
            continue

        if not stack and start_idx is not None:
            snippet = cleaned[start_idx : idx + 1].strip()
            try:
                json.loads(snippet)
                return snippet
            except json.JSONDecodeError:
                start_idx = None
                continue

    return None


def parse_json_content(text: str) -> Any:
    """Parse JSON payload from model response text."""
    payload = extract_json_text(text)
    if not payload:
        raise ValueError("LLM response does not contain valid JSON")
    return json.loads(payload)


class StructuredValidationError(ValueError):
    """结构化解析/校验失败,携带原始文本与错误明细以便上层重试或降级。

    ``ValueError`` 子类,兼容既有 ``except ValueError`` 调用方。
    """

    def __init__(
        self,
        message: str,
        *,
        raw_text: str,
        errors: list[dict[str, Any]] | None = None,
        error_map: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.errors = list(errors or [])
        self.error_map = dict(error_map or {})

    @property
    def feedback_message(self) -> str:
        """面向模型的反馈文案:把校验错误拼成可回注的重试指令。"""
        parts = ["上次输出未通过校验，请仅输出符合 JSON Schema 的 JSON，并按以下问题修正："]
        for key, detail in self.error_map.items():
            parts.append(f"- {key}: {detail}")
        for err in self.errors:
            loc = ".".join(str(p) for p in err.get("loc", [])) or "(root)"
            parts.append(f"- {loc}: {err.get('msg', '')}")
        if self.raw_text:
            parts.append(f"（原输出片段：{self.raw_text[:500]}）")
        return "\n".join(parts)


def parse_model_content(text: str, model_cls: type[TModel]) -> TModel:
    """Parse and validate structured model output from model response text."""
    try:
        parsed = parse_json_content(text)
    except ValueError as e:
        raise StructuredValidationError(
            "LLM response does not contain valid JSON",
            raw_text=text,
            error_map={"parse": str(e)},
        ) from e
    try:
        return model_cls.model_validate(parsed)
    except ValidationError as e:
        raise StructuredValidationError(
            "LLM response failed schema validation",
            raw_text=text,
            errors=[dict(err) for err in e.errors()],
        ) from e


def retry_structured(
    *,
    model_cls: type[TModel],
    responder: Callable[[StructuredValidationError | None], str],
    max_attempts: int = 3,
) -> TModel:
    """受控输出:解析/校验失败时把错误反馈给 responder 重新生成,至多 ``max_attempts`` 次。

    ``responder`` 接收上一次的校验错误(首次为 ``None``),应基于其
    ``feedback_message`` 重新调用 LLM 并返回新的响应文本。
    """
    if max_attempts < 1:
        raise ValueError("max_attempts 必须 >= 1")
    last_err: StructuredValidationError | None = None
    for _ in range(max_attempts):
        text = responder(last_err)
        try:
            return parse_model_content(text, model_cls)
        except StructuredValidationError as e:
            last_err = e
    assert last_err is not None
    raise last_err


async def aretry_structured(
    *,
    model_cls: type[TModel],
    responder: Callable[[StructuredValidationError | None], Awaitable[str]],
    max_attempts: int = 3,
) -> TModel:
    """异步版 ``retry_structured``,``responder`` 为协程函数。"""
    if max_attempts < 1:
        raise ValueError("max_attempts 必须 >= 1")
    last_err: StructuredValidationError | None = None
    for _ in range(max_attempts):
        text = await responder(last_err)
        try:
            return parse_model_content(text, model_cls)
        except StructuredValidationError as e:
            last_err = e
    assert last_err is not None
    raise last_err


def json_schema_instructions(model_cls: type[BaseModel]) -> str:
    """Return concise JSON-schema instructions for structured generation."""
    schema_text = json.dumps(model_cls.model_json_schema(), ensure_ascii=False)
    return "\n".join(
        [
            "请只输出一个 JSON，不要输出 Markdown、解释或额外文本。",
            "输出必须严格满足以下 JSON Schema:",
            schema_text,
        ]
    )
