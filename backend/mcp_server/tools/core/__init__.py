"""核心域 tools 导出"""

from mcp_server.tools.core.llm_service import (
    chat_with_context,
    get_conversation_history,
    list_available_models,
    sync_prompt_templates,
    test_model_connection,
)
from mcp_server.tools.core.system_config import (
    create_system_config,
    delete_system_config,
    list_system_configs,
    patch_system_config,
    update_system_configs,
)
from mcp_server.tools.core.dashboard import get_dashboard_stats
from mcp_server.tools.core.search import global_search
from mcp_server.tools.core.task_queue import (
    delete_schedule,
    delete_task,
    list_completed_tasks,
    list_failed_tasks,
    list_queued_tasks,
    list_scheduled_tasks,
    resubmit_task,
)
from mcp_server.tools.core.poi import (
    generate_poi_complaint,
    generate_report,
    poi_health,
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
    # POI 文档生成
    "poi_health",
    "generate_poi_complaint",
    "generate_report",
]
