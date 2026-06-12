"""验证码识别 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def get_captcha_image(task_id: str) -> dict[str, Any]:
    """获取验证码图片。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/automation/{task_id}/image")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def submit_captcha_answer(task_id: str, answer: str) -> dict[str, Any]:
    """提交验证码答案。answer 为识别出的验证码文本。"""
    return client.post(f"/automation/{task_id}/answer", json={"answer": answer})  # type: ignore[return-value]
