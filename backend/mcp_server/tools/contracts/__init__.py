"""合同域 tools 导出"""

from mcp_server.tools.contracts.archive import (
    clear_all_archive_materials,
    confirm_archive,
    delete_archive_material,
    download_archive_item,
    generate_archive_folder,
    get_archive_checklist,
    learn_archive_rules,
    move_archive_material,
    reorder_archive_materials,
    reset_and_resync_case_materials,
    scale_to_a4,
    sync_case_materials,
    toggle_compact_archive,
)
from mcp_server.tools.contracts.contracts import (
    create_contract,
    create_contract_with_cases,
    delete_contract,
    get_contract,
    get_contract_all_parties,
    list_contracts,
    update_contract,
    update_contract_lawyers,
)
from mcp_server.tools.contracts.folder import (
    browse_folders,
    create_folder_binding,
    delete_folder_binding,
    get_folder_binding,
    list_cloud_storage_accounts,
)
from mcp_server.tools.contracts.folder_scan import (
    confirm_contract_scan,
    get_contract_scan_status,
    get_latest_contract_scan,
    list_contract_scan_subfolders,
    start_contract_scan,
)
from mcp_server.tools.contracts.payments import create_payment, delete_payment, update_payment
from mcp_server.tools.contracts.supplementary import (
    create_supplementary_agreement,
    delete_supplementary_agreement,
    get_supplementary_agreement,
    list_supplementary_agreements,
    update_supplementary_agreement,
)

__all__ = [
    # 合同核心
    "list_contracts",
    "get_contract",
    "create_contract",
    "create_contract_with_cases",
    "update_contract",
    "delete_contract",
    "update_contract_lawyers",
    "get_contract_all_parties",
    # 收款
    "create_payment",
    "update_payment",
    "delete_payment",
    # 补充协议
    "list_supplementary_agreements",
    "get_supplementary_agreement",
    "create_supplementary_agreement",
    "update_supplementary_agreement",
    "delete_supplementary_agreement",
    # 文件夹绑定
    "create_folder_binding",
    "get_folder_binding",
    "delete_folder_binding",
    "browse_folders",
    "list_cloud_storage_accounts",
    # 合同归档
    "learn_archive_rules",
    "get_archive_checklist",
    "download_archive_item",
    "generate_archive_folder",
    "toggle_compact_archive",
    "sync_case_materials",
    "reset_and_resync_case_materials",
    "scale_to_a4",
    "confirm_archive",
    "delete_archive_material",
    "reorder_archive_materials",
    "move_archive_material",
    "clear_all_archive_materials",
    # 合同文件夹扫描
    "start_contract_scan",
    "list_contract_scan_subfolders",
    "get_latest_contract_scan",
    "get_contract_scan_status",
    "confirm_contract_scan",
]
