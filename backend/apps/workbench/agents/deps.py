"""工作台 Agent 依赖注入"""

from dataclasses import dataclass
from typing import Any

@dataclass
class WorkbenchDeps:
    """Agent 运行时依赖，通过 RunContext 注入到工具和提示函数中"""

    session_id: int
    user_id: int | None = None
    llm_model: str = ""
    # 会话摘要（自动压缩长对话后生成）
    conversation_summary: str = ""
    # Token 用量追踪
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
