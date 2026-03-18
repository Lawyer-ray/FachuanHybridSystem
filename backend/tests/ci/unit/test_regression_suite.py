"""Stable regression suite mapped from app-level tests."""

from __future__ import annotations

import pytest
from django.core.cache import cache

from tests.ci._module_loader import expose_test_functions

_STABLE_MODULES: list[str] = [
    "apps.automation.test_sms_parser_lazy_config",
    "apps.cases.test_case_admin_export_guards",
    "apps.cases.test_case_admin_import_wiring",
    "apps.cases.test_case_admin_reminder_export",
    "apps.cases.test_case_admin_service_party_projection",
    "apps.cases.test_case_import_binding",
    "apps.cases.test_case_log_mutation_reminder_command",
    "apps.cases.test_case_log_reminder_projection",
    "apps.cases.test_case_log_schema_reminder_resolver",
    "apps.client.test_client_enterprise_prefill_service",
    "apps.client.test_text_parser",
    "apps.contracts.test_clone_workflow_reminder_export",
    "apps.contracts.test_contract_admin_import_wiring",
    "apps.contracts.test_contract_admin_reminder_export",
    "apps.contracts.test_contract_detail_reminder_export",
    "apps.contracts.test_contract_import_binding",
    "apps.contracts.test_contract_schema_reminder_resolver",
    "apps.core.test_scrub",
    "apps.core.test_shared_reminder_schema",
    "apps.document_recognition.test_case_binding_reminder_bridge",
    "apps.enterprise_data.test_mcp_tool_client",
    "apps.enterprise_data.test_tianyancha_markdown_adapter",
    "apps.organization.test_default_lawyer_selection",
    "apps.organization.test_lawyer_import_service",
    "apps.organization.test_lawyer_service_adapter_compat",
    "apps.organization.test_organization_service_adapter_compat",
    "apps.organization.test_register_view",
    "apps.reminders.test_target_query_injection",
]


@pytest.fixture(autouse=True)
def _clear_ci_cache() -> None:
    cache.clear()


expose_test_functions(globals(), _STABLE_MODULES)
