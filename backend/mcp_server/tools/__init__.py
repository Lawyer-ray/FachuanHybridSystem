"""MCP tools 顶层导出"""

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
from mcp_server.tools.clients import (
    create_client,
    create_property_clue,
    get_client,
    list_clients,
    list_property_clues,
    parse_client_text,
)
from mcp_server.tools.contracts import (
    create_contract,
    create_reminder,
    get_contract,
    get_finance_stats,
    list_contracts,
    list_payments,
    list_reminders,
)
from mcp_server.tools.organization import (
    get_filing_status,
    list_lawyers,
    list_oa_configs,
    list_teams,
    trigger_oa_filing,
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
    "list_payments", "get_finance_stats",
    "list_reminders", "create_reminder",
    # 组织
    "list_lawyers", "list_teams",
    "list_oa_configs", "trigger_oa_filing", "get_filing_status",
]
