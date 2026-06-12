"""组织域 tools 导出"""

from mcp_server.tools.organization.credentials import (
    create_credential,
    delete_credential,
    get_credential,
    list_credentials,
    update_credential,
)
from mcp_server.tools.organization.filing import get_filing_status, list_oa_configs, trigger_oa_filing
from mcp_server.tools.organization.lawfirms import (
    create_lawfirm,
    delete_lawfirm,
    get_lawfirm,
    list_lawfirms,
    update_lawfirm,
)
from mcp_server.tools.organization.lawyers import (
    create_lawyer,
    delete_lawyer,
    get_lawyer,
    list_lawyers,
    update_lawyer,
)
from mcp_server.tools.organization.teams import (
    create_team,
    delete_team,
    get_team,
    list_teams,
    update_team,
)

__all__ = [
    # 律师
    "list_lawyers",
    "get_lawyer",
    "create_lawyer",
    "update_lawyer",
    "delete_lawyer",
    # 律所
    "list_lawfirms",
    "get_lawfirm",
    "create_lawfirm",
    "update_lawfirm",
    "delete_lawfirm",
    # 团队
    "list_teams",
    "get_team",
    "create_team",
    "update_team",
    "delete_team",
    # 账号凭证
    "list_credentials",
    "get_credential",
    "create_credential",
    "update_credential",
    "delete_credential",
    # OA 立案
    "list_oa_configs",
    "trigger_oa_filing",
    "get_filing_status",
]
