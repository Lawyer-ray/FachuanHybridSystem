"""MCP tools 顶层导出"""

from mcp_server.tools.automation import (
    assign_sms_case,
    create_delivery_schedule,
    create_preservation_quote,
    execute_preservation_quote,
    get_court_sms_detail,
    get_preservation_quote,
    list_court_sms,
    list_delivery_schedules,
    list_preservation_quotes,
    query_document_delivery,
    retry_sms_processing,
    submit_court_sms,
)
from mcp_server.tools.cases import (
    add_case_party,
    assign_lawyer,
    create_case,
    create_case_log,
    create_case_number,
    get_case,
    list_case_assignments,
    list_case_logs,
    list_case_numbers,
    list_case_parties,
    list_cases,
    search_cases,
)
from mcp_server.tools.chat_records import (
    create_export,
    create_project,
    get_export_task,
    list_projects,
    list_recordings,
    list_screenshots,
)
from mcp_server.tools.clients import (
    create_client,
    create_property_clue,
    get_client,
    list_clients,
    list_property_clues,
    parse_client_text,
)
from mcp_server.tools.contract_review import (
    get_review_models,
    get_review_status,
    upload_contract_for_review,
)
from mcp_server.tools.contracts import (
    create_contract,
    get_contract,
    list_contracts,
)
from mcp_server.tools.doc_convert import convert_document, list_doc_convert_types
from mcp_server.tools.documents import (
    create_document_template,
    download_contract_document,
    download_contract_folder,
    get_document_template,
    list_document_templates,
    list_folder_templates,
    list_placeholders,
    preview_contract_context,
    preview_placeholders,
)
from mcp_server.tools.enterprise_data import (
    get_company_personnel,
    get_company_profile,
    get_company_risks,
    get_company_shareholders,
    get_person_profile,
    list_enterprise_providers,
    search_bidding_info,
    search_companies,
)
from mcp_server.tools.finance import (
    calculate_interest,
    get_latest_lpr_rate,
    list_lpr_rates,
)
from mcp_server.tools.image_rotation import (
    detect_orientation,
    extract_pdf_pages,
    suggest_rename,
)
from mcp_server.tools.invoice_recognition import (
    download_invoices,
    get_invoice_task_status,
    quick_recognize_invoice,
    upload_invoices,
)
from mcp_server.tools.legal_research import (
    capability_search,
    create_research_task,
    download_all_research_results,
    download_research_result,
    get_research_task,
    list_research_results,
)
from mcp_server.tools.oa_filing import (
    execute_case_import,
    get_case_import_preview,
    get_case_import_session,
    get_client_import_session,
    trigger_case_import,
    trigger_client_import,
)
from mcp_server.tools.organization import (
    get_filing_status,
    list_lawyers,
    list_oa_configs,
    list_teams,
    trigger_oa_filing,
)
from mcp_server.tools.pdf_splitting import (
    cancel_pdf_split,
    confirm_pdf_split,
    create_pdf_split_job,
    download_pdf_split_result,
    get_pdf_split_job,
)
from mcp_server.tools.reminders import (
    create_new_reminder,
    delete_reminder,
    get_finance_stats,
    get_reminder,
    list_all_reminders,
    list_payments,
    list_reminder_types,
    update_reminder,
)

__all__ = [
    # 案件
    "list_cases", "search_cases", "get_case", "create_case",
    "list_case_parties", "add_case_party",
    "list_case_logs", "create_case_log",
    "list_case_numbers", "create_case_number",
    "list_case_assignments", "assign_lawyer",
    # 客户
    "list_clients", "get_client", "create_client", "parse_client_text",
    "list_property_clues", "create_property_clue",
    # 合同
    "list_contracts", "get_contract", "create_contract",
    # 提醒与财务
    "list_all_reminders", "get_reminder", "create_new_reminder",
    "update_reminder", "delete_reminder", "list_reminder_types",
    "list_payments", "get_finance_stats",
    # 组织架构
    "list_lawyers", "list_teams",
    "list_oa_configs", "trigger_oa_filing", "get_filing_status",
    # 企业数据
    "list_enterprise_providers", "search_companies", "get_company_profile",
    "get_company_risks", "get_company_shareholders", "get_company_personnel",
    "get_person_profile", "search_bidding_info",
    # 类案检索
    "create_research_task", "capability_search", "get_research_task",
    "list_research_results", "download_research_result", "download_all_research_results",
    # 自动化
    "submit_court_sms", "list_court_sms", "get_court_sms_detail",
    "assign_sms_case", "retry_sms_processing",
    "create_preservation_quote", "list_preservation_quotes",
    "get_preservation_quote", "execute_preservation_quote",
    "query_document_delivery", "list_delivery_schedules", "create_delivery_schedule",
    # PDF 拆解
    "create_pdf_split_job", "get_pdf_split_job", "confirm_pdf_split",
    "cancel_pdf_split", "download_pdf_split_result",
    # OA 导入
    "trigger_client_import", "get_client_import_session",
    "trigger_case_import", "get_case_import_session",
    "get_case_import_preview", "execute_case_import",
    # 文书转换
    "list_doc_convert_types", "convert_document",
    # 发票识别
    "quick_recognize_invoice", "upload_invoices",
    "get_invoice_task_status", "download_invoices",
    # 聊天记录取证
    "create_project", "list_projects", "list_recordings",
    "list_screenshots", "create_export", "get_export_task",
    # 合同审查
    "upload_contract_for_review", "get_review_status", "get_review_models",
    # 文书生产
    "list_document_templates", "get_document_template", "create_document_template",
    "list_folder_templates", "list_placeholders", "preview_placeholders",
    "preview_contract_context", "download_contract_document", "download_contract_folder",
    # LPR 利率
    "list_lpr_rates", "get_latest_lpr_rate", "calculate_interest",
    # 图片旋转
    "extract_pdf_pages", "detect_orientation", "suggest_rename",
]
