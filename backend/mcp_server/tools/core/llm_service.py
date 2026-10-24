"""LLM 服务 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def chat_with_context(session_id: str, message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """多轮 LLM 对话，支持上下文和会话记忆。

    Args:
        session_id: 会话 ID——同 ID 复用上下文记忆,新话题请换新 ID。
        message: 本轮用户消息全文。
        extra: 可选,透传给后端的附加字段(如模型/温度覆盖),原样并入请求体。
    """
    return client.post(  # type: ignore[no-any-return]
        "/llm/chat",
        json={"session_id": session_id, "message": message, **(extra or {})},
        timeout=180,
    )


def get_conversation_history(session_id: str) -> dict[str, Any]:
    """获取 chat_with_context 会话的历史记录。"""
    return client.get(f"/llm/conversation/{session_id}/history")  # type: ignore[no-any-return]


def sync_prompt_templates() -> dict[str, Any]:
    """同步内置 Prompt 模板到数据库（管理员）。"""
    return client.post("/llm/templates/sync", json={})  # type: ignore[no-any-return]


def list_available_models() -> dict[str, Any]:
    """获取所有已配置的 LLM 模型列表。

    返回 ``{models}``（后端 ``ModelListResponse``）。
    """
    return client.get("/llm/models")  # type: ignore[no-any-return]


def test_model_connection(model_id: str = "") -> dict[str, Any]:
    """测试指定 LLM 模型的连通性（管理员排障用）。"""
    params: dict[str, Any] = {}
    if model_id:
        params["model_id"] = model_id
    return client.post("/llm/test-connection", params=params, json={})  # type: ignore[no-any-return]
