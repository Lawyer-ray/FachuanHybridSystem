import json
from typing import Any, cast

import httpx

from apps.automation.services.ai import get_ollama_base_url


def _parse_streaming_response(text: str, original_error: json.JSONDecodeError) -> dict[str, Any]:
    """解析流式响应，提取最后一个有效的 JSON 行"""
    lines = text.split("\n")
    last_valid_json: dict[str, Any] | None = None
    for line in lines:
        line = line.strip()
        if line:
            try:
                data = json.loads(line)
                if "message" in data:
                    last_valid_json = data
            except json.JSONDecodeError:
                continue
    if last_valid_json:
        return cast(dict[str, Any], last_valid_json)
    raise ValueError(f"无法解析Ollama响应: {original_error!s}\n响应内容: {text[:500]}") from original_error


def _parse_response(resp: httpx.Response) -> dict[str, Any]:
    """解析 Ollama HTTP 响应"""
    try:
        return cast(dict[str, Any], resp.json())
    except json.JSONDecodeError as e:
        text = resp.text.strip()
        if text:
            return _parse_streaming_response(text, e)
        raise ValueError(f"无法解析Ollama响应: {e!s}\n响应内容为空") from e


def chat(model: str, messages: list[dict[str, Any]], base_url: str | None = None) -> dict[str, Any]:
    """
    调用Ollama API进行聊天

    Args:
        model: 模型名称
        messages: 消息列表
        base_url: Ollama服务的基础URL，如果不提供则从 Django settings 读取

    Returns:
        dict: Ollama API返回的JSON响应
    """
    base = base_url or get_ollama_base_url()
    url = base.rstrip("/") + "/api/chat"
    payload = {"model": model, "messages": messages, "stream": False}

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return _parse_response(resp)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise ConnectionError(
                f"Ollama API未找到 (404)。请检查：\n"
                f"1. Ollama服务是否运行在 {base}\n"
                f"2. 模型 '{model}' 是否已安装 (运行: ollama pull {model})\n"
                f"3. API路径是否正确"
            ) from e
        raise ConnectionError(f"Ollama API错误 ({e.response.status_code}): {e.response.text}") from e
    except httpx.ConnectError as e:
        raise ConnectionError(f"无法连接到Ollama服务 ({base})。请确保Ollama服务正在运行。\n错误详情: {e!s}") from e
    except Exception as e:
        raise RuntimeError(f"调用Ollama API时发生错误: {e!s}") from e
