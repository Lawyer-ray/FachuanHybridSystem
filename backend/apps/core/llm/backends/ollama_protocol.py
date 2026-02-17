"""Module for ollama protocol."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

import httpx

from apps.core.llm.exceptions import LLMAPIError

logger = logging.getLogger("apps.core.llm.backends.ollama")


def build_ollama_chat_payload(
    *,
    messages: list[dict[str, str]],
    model: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if options:
        payload["options"] = options
    return payload


def parse_ollama_chat_response(*, resp: httpx.Response, model: str) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], resp.json())
    except json.JSONDecodeError as e:
        text = resp.text.strip()
        if text:
            lines = text.split("\n")
            last_valid_json = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "message" in data:
                    last_valid_json = data

            if last_valid_json:
                return cast(dict[str, Any], last_valid_json)

        logger.warning("Ollama 响应解析失败", extra={"error": str(e), "response_len": len(text)})
        raise LLMAPIError(message=f"无法解析 Ollama 响应: {e!s}", errors={"response_len": len(text)}) from None
