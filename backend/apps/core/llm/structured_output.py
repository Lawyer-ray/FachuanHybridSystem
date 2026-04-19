"""Helpers for extracting structured JSON output from LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar, cast

from pydantic import BaseModel

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


def parse_model_content(text: str, model_cls: type[TModel]) -> TModel:
    """Parse and validate structured model output from model response text."""
    parsed = parse_json_content(text)
    return model_cls.model_validate(parsed)


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
