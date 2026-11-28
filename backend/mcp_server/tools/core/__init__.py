"""核心域 tools 导出"""

from mcp_server.tools.core.agent_attachments import read_agent_attachment
from mcp_server.tools.core.agent_memory import (
    confirm_memories,
    confirm_project_fact,
    forget_memory,
    list_pending_memories,
    recall_memory,
    remember,
    restore_memory,
    save_case_note,
    save_project_note,
)
from mcp_server.tools.core.agent_skills import (
    delete_user_skill,
    get_agent_skill,
    list_my_skills,
    save_user_skill,
    submit_skill_for_review,
)
from mcp_server.tools.core.ask_user import ask_user
from mcp_server.tools.core.dashboard import get_dashboard_stats
from mcp_server.tools.core.identity import get_current_user, get_server_time
from mcp_server.tools.core.llm_service import (
    chat_with_context,
    get_conversation_history,
    list_available_models,
    sync_prompt_templates,
    test_model_connection,
)
from mcp_server.tools.core.search import global_search
from mcp_server.tools.core.subtask import dispatch_research
from mcp_server.tools.core.system_config import (
    create_system_config,
    delete_system_config,
    list_system_configs,
    patch_system_config,
    update_system_configs,
)
from mcp_server.tools.core.task_queue import (
    delete_schedule,
    delete_task,
    list_completed_tasks,
    list_failed_tasks,
    list_queued_tasks,
    list_scheduled_tasks,
    resubmit_task,
)
from mcp_server.tools.core.tasks import (
    create_doc_converter_job,
    get_async_task_status,
    list_doc_converter_jobs,
    list_litigation_sessions,
    list_pending_court_document_tasks,
)

__all__ = [
    # LLM 服务
    "chat_with_context",
    "get_conversation_history",
    "sync_prompt_templates",
    "list_available_models",
    "test_model_connection",
    # 系统配置
    "list_system_configs",
    "update_system_configs",
    "create_system_config",
    "patch_system_config",
    "delete_system_config",
    # 仪表盘
    "get_dashboard_stats",
    # 全局搜索
    "global_search",
    # 任务队列
    "list_queued_tasks",
    "list_completed_tasks",
    "list_failed_tasks",
    "list_scheduled_tasks",
    "delete_task",
    "delete_schedule",
    "resubmit_task",
    # 身份与时间
    "get_current_user",
    "get_server_time",
    # 向律师提问（澄清缺失信息，不是审批）
    "ask_user",
    # 子 agent 只读调研
    "dispatch_research",
    # 记忆（个人 / 团队 / 律所）
    "remember",
    "recall_memory",
    "forget_memory",
    "restore_memory",
    "list_pending_memories",
    "confirm_memories",
    # 项目笔记（团队共享的判断，挂在项目/案件上）
    "save_project_note",
    "save_case_note",
    "confirm_project_fact",
    # 技能（内置 / 个人 / 所内）：读半边零副作用，写半边全部 HIGH 审批
    "get_agent_skill",
    "list_my_skills",
    "save_user_skill",
    "delete_user_skill",
    "submit_skill_for_review",
    # 异步任务统一状态
    "get_async_task_status",
    "list_doc_converter_jobs",
    "create_doc_converter_job",
    "list_litigation_sessions",
    "list_pending_court_document_tasks",
]
