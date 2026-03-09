"""MCP Server 主入口 - 法穿AI案件管理系统"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.case_logs import (
    assign_lawyer,
    create_case_log,
    create_case_number,
    list_case_assignments,
    list_case_logs,
    list_case_numbers,
)
from mcp_server.tools.case_parties import add_case_party, list_case_parties
from mcp_server.tools.cases import create_case, get_case, list_cases, search_cases
from mcp_server.tools.clients import create_client, get_client, list_clients, parse_client_text
from mcp_server.tools.contracts import create_contract, get_contract, list_contracts
from mcp_server.tools.filing import get_filing_status, list_oa_configs, trigger_oa_filing
from mcp_server.tools.finance import get_finance_stats, list_payments
from mcp_server.tools.organization import list_lawyers, list_teams
from mcp_server.tools.property_clues import create_property_clue, list_property_clues
from mcp_server.tools.reminders import create_reminder, list_reminders

mcp = FastMCP("法穿AI案件管理系统")

# 案件
mcp.tool()(list_cases)
mcp.tool()(search_cases)
mcp.tool()(get_case)
mcp.tool()(create_case)

# 案件当事人
mcp.tool()(list_case_parties)
mcp.tool()(add_case_party)

# 案件进展日志
mcp.tool()(list_case_logs)
mcp.tool()(create_case_log)

# 案号
mcp.tool()(list_case_numbers)
mcp.tool()(create_case_number)

# 律师指派
mcp.tool()(list_case_assignments)
mcp.tool()(assign_lawyer)

# 客户
mcp.tool()(list_clients)
mcp.tool()(get_client)
mcp.tool()(create_client)
mcp.tool()(parse_client_text)

# 客户财产线索
mcp.tool()(list_property_clues)
mcp.tool()(create_property_clue)

# 合同
mcp.tool()(list_contracts)
mcp.tool()(get_contract)
mcp.tool()(create_contract)

# 财务
mcp.tool()(list_payments)
mcp.tool()(get_finance_stats)

# 催收提醒
mcp.tool()(list_reminders)
mcp.tool()(create_reminder)

# 组织架构
mcp.tool()(list_lawyers)
mcp.tool()(list_teams)

# OA 立案
mcp.tool()(list_oa_configs)
mcp.tool()(trigger_oa_filing)
mcp.tool()(get_filing_status)
