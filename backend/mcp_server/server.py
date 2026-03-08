"""MCP Server 主入口 - 法穿AI案件管理系统"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.cases import create_case, get_case, list_cases, search_cases
from mcp_server.tools.clients import create_client, get_client, list_clients, parse_client_text
from mcp_server.tools.contracts import get_contract, list_contracts
from mcp_server.tools.filing import get_filing_status, list_oa_configs, trigger_oa_filing

mcp = FastMCP("法穿AI案件管理系统")

# 案件
mcp.tool()(list_cases)
mcp.tool()(search_cases)
mcp.tool()(get_case)
mcp.tool()(create_case)

# 客户
mcp.tool()(list_clients)
mcp.tool()(get_client)
mcp.tool()(create_client)
mcp.tool()(parse_client_text)

# 合同
mcp.tool()(list_contracts)
mcp.tool()(get_contract)

# OA 立案
mcp.tool()(list_oa_configs)
mcp.tool()(trigger_oa_filing)
mcp.tool()(get_filing_status)
