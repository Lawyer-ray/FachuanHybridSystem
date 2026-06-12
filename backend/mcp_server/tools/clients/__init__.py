"""客户域 tools 导出"""

from mcp_server.tools.clients.clients import (
    create_client,
    delete_client,
    get_client,
    get_identity_doc_task,
    list_clients,
    list_clients_with_docs,
    merge_id_card_manual,
    parse_client_text,
    submit_identity_doc_recognition,
    update_client,
)
from mcp_server.tools.clients.enterprise import enterprise_prefill, enterprise_search
from mcp_server.tools.clients.identity_docs import delete_identity_doc, get_identity_doc
from mcp_server.tools.clients.property_clues import (
    create_property_clue,
    delete_property_clue,
    get_property_clue,
    get_property_clue_content_template,
    list_property_clues,
    update_property_clue,
)
from mcp_server.tools.clients.validation import check_oa_credential, validate_id_card

__all__ = [
    "list_clients",
    "get_client",
    "create_client",
    "parse_client_text",
    "update_client",
    "delete_client",
    "list_clients_with_docs",
    "get_identity_doc_task",
    "submit_identity_doc_recognition",
    "merge_id_card_manual",
    "enterprise_search",
    "enterprise_prefill",
    "get_identity_doc",
    "delete_identity_doc",
    "list_property_clues",
    "create_property_clue",
    "get_property_clue",
    "update_property_clue",
    "delete_property_clue",
    "get_property_clue_content_template",
    "validate_id_card",
    "check_oa_credential",
]
