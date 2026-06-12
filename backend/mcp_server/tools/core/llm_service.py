"""LLM 服务 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def chat_with_context(session_id: str, message: str, **extra: Any) -> dict[str, Any]:
    """多轮 LLM 对话，支持上下文和会话记忆。"""
    return client.post("/llm/chat", json={"session_id": session_id, "message": message, **extra})  # type: ignore[return-value]


def get_conversation_history(session_id: str) -> dict[str, Any]:
    """获取对话历史记录。"""
    return client.get(f"/llm/conversation/{session_id}/history")  # type: ignore[return-value]


def sync_prompt_templates() -> dict[str, Any]:
    """同步内置 Prompt 模板到数据库（管理员）。"""
    return client.post("/llm/templates/sync", json={})  # type: ignore[return-value]


def list_available_models() -> list[dict[str, Any]]:
    """获取所有已配置的 LLM 模型列表。"""
    return client.get("/llm/models")  # type: ignore[return-value]


def test_model_connection(model_id: int | None = None) -> dict[str, Any]:
    """测试指定模型的连通性。"""
    params: dict[str, Any] = {}
    if model_id is not None:
        params["model_id"] = model_id
    return client.post("/llm/test-connection", params=params, json={})  # type: ignore[return-value]
