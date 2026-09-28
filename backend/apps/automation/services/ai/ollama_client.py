from typing import Any

from apps.core.interfaces import ServiceLocator


def chat(model: str, messages: list[dict[str, Any]], base_url: str | None = None) -> dict[str, Any]:  # pragma: no cover
    """
    兼容旧接口：通过统一 LLM 服务聊天。

    Args:
        model: 模型名称；含 ":" 走本地 Ollama，其余按名字路由到 AI 平台
        messages: 消息列表
        base_url: 兼容保留参数，当前由统一 LLM 配置接管

    Returns:
        dict: 与旧 Ollama API 响应同构的 dict
    """
    _ = base_url  # 保留参数兼容，不再直接使用
    llm_service = ServiceLocator.get_llm_service()
    llm_response = llm_service.chat(messages=messages, model=model)
    return {
        "model": llm_response.model,
        "message": {"content": llm_response.content},
        "backend": llm_response.backend,
        "prompt_eval_count": llm_response.prompt_tokens,
        "eval_count": llm_response.completion_tokens,
    }
