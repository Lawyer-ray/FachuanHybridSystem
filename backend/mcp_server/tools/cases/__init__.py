"""案件域 tools 导出"""

from mcp_server.tools.cases.assignments import (
    assign_lawyer,
    delete_case_assignment,
    get_case_assignment,
    list_case_assignments,
    update_case_assignment,
)
from mcp_server.tools.cases.case_folder import (
    browse_case_folders,
    create_case_folder_binding,
    delete_case_folder_binding,
    get_case_folder_binding,
    get_contract_folder_path,
    list_case_cloud_storage_accounts,
)
from mcp_server.tools.cases.cases import (
    create_case,
    create_full_case,
    delete_case,
    get_case,
    list_cases,
    search_cases,
    update_case,
)
from mcp_server.tools.cases.cause_court import (
    get_cause,
    list_causes_data,
    list_causes_tree,
    list_courts_data,
)
from mcp_server.tools.cases.folder_scan import (
    create_scan_stage,
    get_scan_status,
    list_scan_subfolders,
    start_folder_scan,
)
from mcp_server.tools.cases.grants import (
    create_grant,
    delete_grant,
    get_grant,
    list_grants,
    update_grant,
)
from mcp_server.tools.cases.litigation_fee import calculate_litigation_fee
from mcp_server.tools.cases.logs import (
    create_case_log,
    delete_case_log,
    get_case_log,
    list_case_logs,
    update_case_log,
)
from mcp_server.tools.cases.materials import (
    bind_materials,
    delete_all_materials,
    delete_material,
    list_bind_candidates,
    rename_material_group,
    save_group_order,
)
from mcp_server.tools.cases.numbers import (
    create_case_number,
    delete_case_number,
    get_case_number,
    list_case_numbers,
    update_case_number,
)
from mcp_server.tools.cases.parties import (
    add_case_party,
    delete_case_party,
    get_case_party,
    list_case_parties,
    update_case_party,
)
from mcp_server.tools.cases.template_binding import (
    create_template_binding,
    delete_template_binding,
    generate_case_template,
    list_available_templates,
    list_template_bindings,
    unified_generate,
)

__all__ = [
    # 案件 CRUD
    "list_cases",
    "search_cases",
    "get_case",
    "create_case",
    "update_case",
    "delete_case",
    "create_full_case",
    # 案件当事人
    "list_case_parties",
    "add_case_party",
    "get_case_party",
    "update_case_party",
    "delete_case_party",
    # 案件进展日志
    "list_case_logs",
    "create_case_log",
    "get_case_log",
    "update_case_log",
    "delete_case_log",
    # 案号
    "list_case_numbers",
    "create_case_number",
    "get_case_number",
    "update_case_number",
    "delete_case_number",
    # 律师指派
    "list_case_assignments",
    "assign_lawyer",
    "get_case_assignment",
    "update_case_assignment",
    "delete_case_assignment",
    # 访问权限
    "list_grants",
    "create_grant",
    "get_grant",
    "update_grant",
    "delete_grant",
    # 案由/法院数据
    "list_causes_data",
    "list_causes_tree",
    "get_cause",
    "list_courts_data",
    # 诉讼费
    "calculate_litigation_fee",
    # 案件材料
    "list_bind_candidates",
    "bind_materials",
    "save_group_order",
    "rename_material_group",
    "delete_material",
    "delete_all_materials",
    # 文件夹扫描
    "start_folder_scan",
    "list_scan_subfolders",
    "get_scan_status",
    "create_scan_stage",
    # 文件夹绑定
    "create_case_folder_binding",
    "get_case_folder_binding",
    "delete_case_folder_binding",
    "get_contract_folder_path",
    "browse_case_folders",
    "list_case_cloud_storage_accounts",
    # 模板绑定
    "list_template_bindings",
    "create_template_binding",
    "delete_template_binding",
    "list_available_templates",
    "generate_case_template",
    "unified_generate",
]
