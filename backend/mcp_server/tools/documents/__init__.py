"""文书生产域 tools 导出"""

from mcp_server.tools.documents.authorization import (
    download_authorization_package,
    download_authority_letter,
    download_legal_rep_certificate,
    download_power_of_attorney,
    download_power_of_attorney_combined,
)
from mcp_server.tools.documents.documents import (
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
from mcp_server.tools.documents.evidence import (
    reorder_evidence_items,
)
from mcp_server.tools.documents.external_templates import (
    analyze_template,
    confirm_mappings,
    create_mapping,
    delete_mapping,
    get_custom_fields,
    get_fill_history,
    get_preview_html,
    get_statistics,
    list_mappings,
    match_templates,
    preview_fill,
    update_mapping,
)
from mcp_server.tools.documents.folder_template_ops import (
    create_folder_template,
    delete_folder_template,
    get_folder_template,
    update_folder_template,
    validate_folder_structure,
)
from mcp_server.tools.documents.generation_ops import (
    delete_archive_overrides,
    download_supplementary_agreement,
    get_archive_overrides,
    preview_archive_context,
    preview_supplementary_agreement_context,
    save_archive_overrides,
)
from mcp_server.tools.documents.litigation import (
    download_litigation_document,
    generate_complaint,
    generate_defense,
    preview_litigation_context,
)
from mcp_server.tools.documents.placeholder_ops import (
    create_placeholder,
    delete_placeholder,
    get_placeholder,
    get_placeholder_by_key,
    update_placeholder,
)
from mcp_server.tools.documents.preservation import (
    download_delay_delivery_application,
    download_full_preservation_package,
    download_preservation_application,
)
from mcp_server.tools.documents.template_ops import (
    delete_document_template,
    extract_template_placeholders,
    get_undefined_placeholders,
    list_template_library_files,
    update_document_template,
)

__all__ = [
    # 文书生产 - 基础查询
    "list_document_templates",
    "get_document_template",
    "create_document_template",
    "list_folder_templates",
    "list_placeholders",
    "preview_placeholders",
    "preview_contract_context",
    "download_contract_document",
    "download_contract_folder",
    # 文书生产 - 模板操作
    "update_document_template",
    "delete_document_template",
    "extract_template_placeholders",
    "get_undefined_placeholders",
    "list_template_library_files",
    # 文件夹模板操作
    "get_folder_template",
    "create_folder_template",
    "update_folder_template",
    "delete_folder_template",
    "validate_folder_structure",
    # 替换词操作
    "get_placeholder",
    "get_placeholder_by_key",
    "create_placeholder",
    "update_placeholder",
    "delete_placeholder",
    # 文档生成操作
    "preview_supplementary_agreement_context",
    "preview_archive_context",
    "get_archive_overrides",
    "save_archive_overrides",
    "delete_archive_overrides",
    "download_supplementary_agreement",
    # 诉讼文书生成
    "generate_complaint",
    "generate_defense",
    "preview_litigation_context",
    "download_litigation_document",
    # 授权委托材料
    "download_authority_letter",
    "download_legal_rep_certificate",
    "download_power_of_attorney_combined",
    "download_authorization_package",
    "download_power_of_attorney",
    # 财产保全材料
    "download_preservation_application",
    "download_delay_delivery_application",
    "download_full_preservation_package",
    # 外部模板
    "analyze_template",
    "confirm_mappings",
    "preview_fill",
    "match_templates",
    "get_custom_fields",
    "get_fill_history",
    "get_statistics",
    "get_preview_html",
    "list_mappings",
    "create_mapping",
    "update_mapping",
    "delete_mapping",
    # 证据管理
    "reorder_evidence_items",
]
