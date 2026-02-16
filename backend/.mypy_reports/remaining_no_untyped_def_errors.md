# 剩余no-untyped-def错误报告

总错误数: 105
涉及文件数: 66

## 按错误类型分类

- missing_args: 74
- missing_return: 26
- missing_annotation: 5

## 错误最多的前20个文件

- apps/core/llm/backends/__init__.py: 5
- apps/automation/services/token/login_acquisition_flow.py: 5
- apps/core/throttling.py: 4
- apps/automation/services/token/history_recorder.py: 4
- apps/automation/services/document_delivery/document_delivery_service.py: 4
- apps/cases/services/log/case_log_mutation_service.py: 3
- apps/core/llm/client.py: 3
- apps/automation/services/token/account_selection_strategy.py: 3
- apps/automation/services/document_delivery/playwright/document_delivery_playwright_service.py: 3
- apps/automation/services/document_delivery/api/document_delivery_api_service.py: 3
- apps/core/config/steering_performance_monitor.py: 2
- apps/core/monitoring.py: 2
- apps/cases/services/log/case_log_query_service.py: 2
- apps/core/management/commands/start_resource_monitor.py: 2
- apps/cases/services/log/case_log_attachment_service.py: 2
- apps/documents/services/folder_template/id_service.py: 2
- apps/documents/services/evidence/evidence_file_service.py: 2
- apps/automation/services/token/court_login_gateway.py: 2
- apps/documents/services/generation/litigation_context_builder.py: 2
- apps/automation/services/document_delivery/processor/document_delivery_processor.py: 2

## 详细错误列表

### apps/core/llm/backends/__init__.py (5 个错误)

- Line 24: Function is missing a type annotation for one or more arguments
- Line 33: Function is missing a type annotation for one or more arguments
- Line 41: Function is missing a type annotation for one or more arguments
- Line 44: Function is missing a type annotation for one or more arguments
- Line 52: Function is missing a type annotation for one or more arguments

### apps/automation/services/token/login_acquisition_flow.py (5 个错误)

- Line 36: Function is missing a type annotation for one or more arguments
- Line 56: Function is missing a type annotation for one or more arguments
- Line 69: Function is missing a type annotation for one or more arguments
- Line 86: Function is missing a type annotation for one or more arguments
- Line 105: Function is missing a type annotation for one or more arguments

### apps/core/throttling.py (4 个错误)

- Line 105: Function is missing a type annotation
- Line 108: Function is missing a return type annotation
- Line 108: Function is missing a type annotation for one or more arguments
- Line 124: Function is missing a type annotation

### apps/automation/services/token/history_recorder.py (4 个错误)

- Line 89: Function is missing a return type annotation
- Line 112: Function is missing a return type annotation
- Line 141: Function is missing a return type annotation
- Line 168: Function is missing a return type annotation

### apps/automation/services/document_delivery/document_delivery_service.py (4 个错误)

- Line 328: Function is missing a return type annotation
- Line 770: Function is missing a return type annotation
- Line 828: Function is missing a return type annotation
- Line 913: Function is missing a return type annotation

### apps/cases/services/log/case_log_mutation_service.py (3 个错误)

- Line 20: Function is missing a type annotation for one or more arguments
- Line 55: Function is missing a type annotation for one or more arguments
- Line 88: Function is missing a type annotation for one or more arguments

### apps/core/llm/client.py (3 个错误)

- Line 14: Function is missing a type annotation for one or more arguments
- Line 40: Function is missing a type annotation for one or more arguments
- Line 57: Function is missing a type annotation for one or more arguments

### apps/automation/services/token/account_selection_strategy.py (3 个错误)

- Line 129: Function is missing a return type annotation
- Line 162: Function is missing a return type annotation
- Line 249: Function is missing a return type annotation

### apps/automation/services/document_delivery/playwright/document_delivery_playwright_service.py (3 个错误)

- Line 455: Function is missing a return type annotation
- Line 601: Function is missing a return type annotation
- Line 869: Function is missing a return type annotation

### apps/automation/services/document_delivery/api/document_delivery_api_service.py (3 个错误)

- Line 291: Function is missing a return type annotation
- Line 330: Function is missing a return type annotation
- Line 510: Function is missing a return type annotation

### apps/core/config/steering_performance_monitor.py (2 个错误)

- Line 191: Function is missing a return type annotation
- Line 412: Function is missing a return type annotation

### apps/core/monitoring.py (2 个错误)

- Line 44: Function is missing a return type annotation
- Line 44: Function is missing a type annotation for one or more arguments

### apps/cases/services/log/case_log_query_service.py (2 个错误)

- Line 24: Function is missing a type annotation for one or more arguments
- Line 48: Function is missing a type annotation for one or more arguments

### apps/core/management/commands/start_resource_monitor.py (2 个错误)

- Line 20: Function is missing a type annotation for one or more arguments
- Line 25: Function is missing a type annotation for one or more arguments

### apps/cases/services/log/case_log_attachment_service.py (2 个错误)

- Line 19: Function is missing a type annotation for one or more arguments
- Line 47: Function is missing a type annotation for one or more arguments

### apps/documents/services/folder_template/id_service.py (2 个错误)

- Line 17: Function is missing a type annotation for one or more arguments
- Line 61: Function is missing a type annotation for one or more arguments

### apps/documents/services/evidence/evidence_file_service.py (2 个错误)

- Line 22: Function is missing a type annotation for one or more arguments
- Line 74: Function is missing a type annotation for one or more arguments

### apps/automation/services/token/court_login_gateway.py (2 个错误)

- Line 12: Function is missing a type annotation for one or more arguments
- Line 17: Function is missing a type annotation for one or more arguments

### apps/documents/services/generation/litigation_context_builder.py (2 个错误)

- Line 60: Function is missing a type annotation for one or more arguments
- Line 84: Function is missing a type annotation for one or more arguments

### apps/automation/services/document_delivery/processor/document_delivery_processor.py (2 个错误)

- Line 86: Function is missing a return type annotation
- Line 142: Function is missing a return type annotation

### apps/cases/services/chat/case_chat_service.py (2 个错误)

- Line 51: Function is missing a type annotation for one or more arguments
- Line 56: Function is missing a type annotation for one or more arguments

### apps/automation/services/document_delivery/document_delivery_schedule_service.py (2 个错误)

- Line 134: Function is missing a type annotation for one or more arguments
- Line 251: Function is missing a return type annotation

### apps/core/config/providers/yaml.py (1 个错误)

- Line 120: Function is missing a type annotation

### apps/core/management/commands/check_db_performance.py (1 个错误)

- Line 11: Function is missing a type annotation for one or more arguments

### apps/core/management/commands/analyze_performance.py (1 个错误)

- Line 23: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/setup_document_delivery_schedule.py (1 个错误)

- Line 25: Function is missing a type annotation for one or more arguments

### apps/client/services/id_card_merge/image_io.py (1 个错误)

- Line 35: Function is missing a type annotation for one or more arguments

### apps/core/config/steering_integration.py (1 个错误)

- Line 460: Function is missing a return type annotation

### apps/client/management/commands/normalize_client_media_paths.py (1 个错误)

- Line 10: Function is missing a type annotation for one or more arguments

### apps/organization/forms.py (1 个错误)

- Line 18: Function is missing a type annotation for one or more arguments

### apps/automation/apps.py (1 个错误)

- Line 53: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/download_ocr_models.py (1 个错误)

- Line 21: Function is missing a type annotation for one or more arguments

### apps/automation/services/scraper/sites/court_zxfw_login_flow.py (1 个错误)

- Line 125: Function is missing a type annotation for one or more arguments

### apps/automation/services/scraper/sites/court_zxfw_baoquan_token_fetcher.py (1 个错误)

- Line 79: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/bench_http.py (1 个错误)

- Line 43: Function is missing a type annotation for one or more arguments

### apps/core/exceptions/__init__.py (1 个错误)

- Line 62: Function is missing a type annotation for one or more arguments

### apps/core/services/system_config_service.py (1 个错误)

- Line 26: Function is missing a type annotation for one or more arguments

### apps/core/llm/prompts/base.py (1 个错误)

- Line 93: Function is missing a type annotation for one or more arguments

### apps/documents/services/placeholders/case/case_common_service.py (1 个错误)

- Line 129: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/smoke_check.py (1 个错误)

- Line 54: Function is missing a type annotation for one or more arguments

### apps/cases/services/log/case_log_version_service.py (1 个错误)

- Line 14: Function is missing a type annotation for one or more arguments

### apps/core/management/commands/encrypt_system_config_secrets.py (1 个错误)

- Line 13: Function is missing a type annotation for one or more arguments

### apps/documents/services/pdf_merge_service.py (1 个错误)

- Line 92: Function is missing a type annotation for one or more arguments

### apps/documents/services/generation_service.py (1 个错误)

- Line 137: Function is missing a type annotation for one or more arguments

### apps/documents/management/commands/init_document_system.py (1 个错误)

- Line 23: Function is missing a type annotation for one or more arguments

### apps/documents/management/commands/create_default_prompt_versions.py (1 个错误)

- Line 17: Function is missing a type annotation for one or more arguments

### apps/core/management/commands/init_system_config.py (1 个错误)

- Line 18: Function is missing a type annotation for one or more arguments

### apps/automation/services/chat/feishu_provider.py (1 个错误)

- Line 655: Function is missing a return type annotation

### apps/documents/services/folder_template/repair_service.py (1 个错误)

- Line 45: Function is missing a type annotation for one or more arguments

### apps/documents/services/folder_template/command_service.py (1 个错误)

- Line 25: Function is missing a type annotation for one or more arguments

### apps/documents/management/commands/fix_folder_template_ids.py (1 个错误)

- Line 17: Function is missing a type annotation for one or more arguments

### apps/documents/usecases/folder_template/folder_template_usecases.py (1 个错误)

- Line 37: Function is missing a type annotation for one or more arguments

### apps/documents/services/folder_service.py (1 个错误)

- Line 64: Function is missing a type annotation for one or more arguments

### apps/automation/services/scraper/sites/court_zxfw.py (1 个错误)

- Line 87: Function is missing a type annotation

### apps/automation/services/scraper/court_document_service.py (1 个错误)

- Line 22: Function is missing a type annotation for one or more arguments

### apps/automation/services/insurance/preservation_quote_service.py (1 个错误)

- Line 439: Function is missing a type annotation

### apps/cases/services/template/folder_binding_service.py (1 个错误)

- Line 157: Function is missing a type annotation for one or more arguments

### apps/cases/services/data/cause_court_data_service.py (1 个错误)

- Line 106: Function is missing a type annotation for one or more arguments

### apps/cases/management/commands/sync_case_assignments_from_contracts.py (1 个错误)

- Line 13: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/recover_court_sms_tasks.py (1 个错误)

- Line 26: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/process_pending_tasks.py (1 个错误)

- Line 19: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/optimize_token_performance.py (1 个错误)

- Line 27: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/clear_token_cache.py (1 个错误)

- Line 20: Function is missing a type annotation for one or more arguments

### apps/documents/management/commands/init_folder_templates.py (1 个错误)

- Line 20: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/init_document_delivery.py (1 个错误)

- Line 24: Function is missing a type annotation for one or more arguments

### apps/automation/management/commands/execute_document_delivery_schedules.py (1 个错误)

- Line 25: Function is missing a type annotation for one or more arguments

