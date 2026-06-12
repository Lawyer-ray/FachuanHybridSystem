"""自动化域 tools 导出"""

from mcp_server.tools.automation.auto_namer import auto_namer_process, auto_namer_process_by_path
from mcp_server.tools.automation.captcha import get_captcha_image, submit_captcha_answer
from mcp_server.tools.automation.court_filing import (
    execute_court_filing,
    get_court_filing_case_info,
    get_court_filing_session,
)
from mcp_server.tools.automation.court_guarantee import (
    bind_guarantee_quote,
    delete_guarantee_binding,
    delete_guarantee_quote,
    ensure_guarantee_quote,
    execute_guarantee,
    get_guarantee_case_info,
    get_guarantee_session,
    retry_guarantee_quote,
)
from mcp_server.tools.automation.court_sms import (
    assign_sms_case,
    delete_court_sms,
    download_sms_document,
    download_sms_documents,
    get_court_sms_detail,
    list_court_sms,
    retry_sms_processing,
    submit_court_sms,
)
from mcp_server.tools.automation.document_delivery import (
    create_delivery_schedule,
    get_delivery_schedule,
    list_delivery_schedules,
    query_document_delivery,
    update_delivery_schedule,
)
from mcp_server.tools.automation.document_processor import process_document, process_document_by_path
from mcp_server.tools.automation.main_api import ai_ollama, get_automation_config, get_automation_status
from mcp_server.tools.automation.performance import (
    cleanup_resources,
    clear_cache,
    get_cache_statistics,
    get_performance_metrics,
    get_resource_usage,
    get_statistics_report,
    health_check,
    optimize_concurrency,
    reset_performance_metrics,
    warm_up_cache,
)
from mcp_server.tools.automation.preservation_quote import (
    create_preservation_quote,
    execute_preservation_quote,
    get_preservation_quote,
    list_preservation_quotes,
    retry_preservation_quote,
)

__all__ = [
    # 法院短信
    "submit_court_sms",
    "list_court_sms",
    "get_court_sms_detail",
    "assign_sms_case",
    "retry_sms_processing",
    "delete_court_sms",
    "download_sms_documents",
    "download_sms_document",
    # 财产保全询价
    "create_preservation_quote",
    "list_preservation_quotes",
    "get_preservation_quote",
    "execute_preservation_quote",
    "retry_preservation_quote",
    # 文书送达
    "query_document_delivery",
    "list_delivery_schedules",
    "create_delivery_schedule",
    "get_delivery_schedule",
    "update_delivery_schedule",
    # 验证码
    "get_captcha_image",
    "submit_captcha_answer",
    # 自动命名
    "auto_namer_process",
    "auto_namer_process_by_path",
    # 网上立案
    "get_court_filing_case_info",
    "get_court_filing_session",
    "execute_court_filing",
    # 诉讼保全
    "get_guarantee_case_info",
    "get_guarantee_session",
    "execute_guarantee",
    "ensure_guarantee_quote",
    "bind_guarantee_quote",
    "delete_guarantee_quote",
    "retry_guarantee_quote",
    "delete_guarantee_binding",
    # 性能监控
    "health_check",
    "get_performance_metrics",
    "get_statistics_report",
    "get_resource_usage",
    "get_cache_statistics",
    "optimize_concurrency",
    "warm_up_cache",
    "clear_cache",
    "reset_performance_metrics",
    "cleanup_resources",
    # 文档处理器
    "process_document",
    "process_document_by_path",
    # 自动化主 API
    "ai_ollama",
    "get_automation_config",
    "get_automation_status",
]
