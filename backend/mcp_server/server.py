"""MCP Server 主入口 - 法穿SI Copilot"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from apps.agent.services.approval import RiskLevel, classify_risk
from mcp_server.tools import (
    add_case_party,
    add_contract_party,
    analyze_template,
    approve_workflow_step,
    assign_lawyer,
    assign_sms_case,
    auto_namer_process_by_path,
    batch_create_cases,
    batch_create_clients,
    bind_materials,
    browse_case_folders,
    browse_folders,
    calculate_interest,
    calculate_litigation_fee,
    cancel_conversion_job,
    cancel_extract_recording,
    cancel_pdf_split,
    cancel_workflow,
    capability_search,
    chat_with_context,
    check_law_references,
    check_oa_credential,
    cleanup_resources,
    clear_all_archive_materials,
    clear_cache,
    complete_reminders,
    confirm_archive,
    confirm_contract_scan,
    confirm_mappings,
    confirm_party,
    confirm_pdf_split,
    convert_document,
    create_case,
    create_case_folder_binding,
    create_case_log,
    create_case_number,
    create_client,
    create_contact,
    create_contract,
    create_contract_with_cases,
    create_credential,
    create_doc_converter_job,
    create_document_template,
    create_export,
    create_folder_binding,
    create_folder_template,
    create_full_case,
    create_grant,
    create_lawfirm,
    create_lawyer,
    create_mapping,
    create_message_source,
    create_new_reminder,
    create_payment,
    create_pdf_split_job,
    create_placeholder,
    create_project,
    create_property_clue,
    create_research_task,
    create_scan_stage,
    create_supplementary_agreement,
    create_system_config,
    create_team,
    create_template_binding,
    create_workflow_template,
    delete_all_materials,
    delete_archive_material,
    delete_archive_overrides,
    delete_case,
    delete_case_assignment,
    delete_case_folder_binding,
    delete_case_log,
    delete_case_number,
    delete_case_party,
    delete_client,
    delete_contact,
    delete_contract,
    delete_conversion_job,
    delete_court_sms,
    delete_credential,
    delete_document_template,
    delete_folder_binding,
    delete_folder_template,
    delete_grant,
    delete_identity_doc,
    delete_lawfirm,
    delete_lawyer,
    delete_mapping,
    delete_material,
    delete_message_source,
    delete_payment,
    delete_placeholder,
    delete_property_clue,
    delete_recording,
    delete_reminder,
    delete_reminders,
    delete_schedule,
    delete_supplementary_agreement,
    delete_system_config,
    delete_task,
    delete_team,
    delete_template_binding,
    delete_workflow_run,
    delete_workflow_template,
    detect_orientation,
    detect_single_page_orientation,
    doc_converter_health_check,
    download_all_research_results,
    download_archive_item,
    download_authority_letter,
    download_authorization_package,
    download_contract_document,
    download_contract_folder,
    download_converted_files,
    download_delay_delivery_application,
    download_export,
    download_full_preservation_package,
    download_inbox_attachment,
    download_invoices,
    download_legal_rep_certificate,
    download_litigation_document,
    download_normalized_result,
    download_pdf_split_raw,
    download_pdf_split_result,
    download_power_of_attorney,
    download_power_of_attorney_combined,
    download_preservation_application,
    download_research_result,
    download_review_original,
    download_review_result,
    download_sms_document,
    download_sms_documents,
    download_supplementary_agreement,
    duplicate_workflow_template,
    enterprise_prefill,
    enterprise_search,
    execute_case_import,
    export_rotated_images,
    export_rotated_pdf,
    extract_document_text,
    extract_pdf_pages,
    extract_recording,
    extract_template_placeholders,
    fetch_url,
    fill_templates,
    generate_archive_folder,
    generate_case_template,
    generate_complaint,
    generate_defense,
    get_agent_skill,
    get_archive_checklist,
    get_archive_overrides,
    get_async_task_status,
    get_automation_config,
    get_automation_status,
    get_cache_statistics,
    get_captcha_image,
    get_case,
    get_case_assignment,
    get_case_folder_binding,
    get_case_import_preview,
    get_case_import_session,
    get_case_log,
    get_case_number,
    get_case_party,
    get_cause,
    get_client,
    get_client_import_session,
    get_client_related_items,
    get_company_personnel,
    get_company_profile,
    get_company_risks,
    get_company_shareholders,
    get_contact,
    get_contract,
    get_contract_all_parties,
    get_contract_folder_path,
    get_contract_scan_status,
    get_conversation_history,
    get_conversion_progress,
    get_court_sms_detail,
    get_credential,
    get_current_user,
    get_custom_fields,
    get_dashboard_stats,
    get_document_parsing_task,
    get_document_template,
    get_export_statuses,
    get_export_task,
    get_export_types,
    get_filing_status,
    get_fill_history,
    get_finance_stats,
    get_folder_binding,
    get_folder_template,
    get_grant,
    get_identity_doc,
    get_identity_doc_task,
    get_inbox_message,
    get_invoice_task_status,
    get_latest_contract_scan,
    get_latest_lpr_rate,
    get_lawfirm,
    get_lawyer,
    get_lpr_sync_status,
    get_message_source,
    get_pdf_split_job,
    get_pdf_split_page_preview,
    get_performance_metrics,
    get_person_profile,
    get_placeholder,
    get_placeholder_by_key,
    get_preview_html,
    get_property_clue,
    get_property_clue_content_template,
    get_recording,
    get_reminder,
    get_reminder_calendar,
    get_research_task,
    get_resource_usage,
    get_review_models,
    get_review_status,
    get_scan_status,
    get_server_time,
    get_statistics,
    get_statistics_report,
    get_step_registry,
    get_step_registry_flat,
    get_supplementary_agreement,
    get_target_options,
    get_team,
    get_undefined_placeholders,
    get_workflow_detail,
    get_workflow_template,
    global_search,
    health_check,
    learn_archive_rules,
    list_all_reminders,
    list_available_models,
    list_available_templates,
    list_bind_candidates,
    list_case_assignments,
    list_case_cloud_storage_accounts,
    list_case_folder_entries,
    list_case_logs,
    list_case_numbers,
    list_case_parties,
    list_cases,
    list_causes_data,
    list_causes_tree,
    list_clients,
    list_clients_with_docs,
    list_cloud_storage_accounts,
    list_completed_tasks,
    list_contacts,
    list_contract_folder_entries,
    list_contract_scan_subfolders,
    list_contracts,
    list_court_sms,
    list_courts_data,
    list_credentials,
    list_doc_convert_types,
    list_doc_converter_jobs,
    list_document_parsing_records,
    list_document_templates,
    list_enterprise_providers,
    list_failed_tasks,
    list_folder_files,
    list_folder_templates,
    list_grants,
    list_inbox_messages,
    list_lawfirms,
    list_lawyers,
    list_litigation_sessions,
    list_lpr_rates,
    list_mappings,
    list_message_sources,
    list_oa_configs,
    list_payments,
    list_pending_court_document_tasks,
    list_placeholders,
    list_projects,
    list_property_clues,
    list_queued_tasks,
    list_recordings,
    list_reminder_types,
    list_reminders_by_target,
    list_research_results,
    list_scan_subfolders,
    list_scheduled_tasks,
    list_screenshots,
    list_supplementary_agreements,
    list_system_configs,
    list_teams,
    list_template_bindings,
    list_template_library_files,
    list_upcoming_deadlines,
    list_workflow_templates,
    list_workflows,
    match_templates,
    merge_id_card_manual,
    mortgage_amortize,
    mortgage_default_calculate,
    move_archive_material,
    normalize_contract_format,
    optimize_concurrency,
    parse_client_text,
    parse_document,
    parse_reminders_from_text,
    patch_system_config,
    preview_archive_context,
    preview_contract_context,
    preview_fill,
    preview_inbox_attachment,
    preview_litigation_context,
    preview_placeholders,
    preview_supplementary_agreement_context,
    process_document,
    process_document_by_path,
    quick_recognize_invoice,
    read_agent_attachment,
    read_folder_file,
    remove_contract_party,
    rename_inbox_attachment,
    rename_material_group,
    reorder_archive_materials,
    reorder_evidence_items,
    reorder_screenshots,
    reset_and_resync_case_materials,
    reset_extract_recording,
    reset_performance_metrics,
    resubmit_task,
    retry_sms_processing,
    save_archive_overrides,
    save_group_order,
    save_to_directory,
    scale_to_a4,
    search_bidding_info,
    search_cases,
    search_companies,
    search_contacts,
    start_contract_scan,
    start_folder_scan,
    start_workflow,
    start_workflow_from_steps,
    submit_captcha_answer,
    submit_court_sms,
    submit_identity_doc_recognition,
    suggest_rename,
    sync_all_message_sources,
    sync_case_materials,
    sync_lpr_rates,
    sync_message_source,
    sync_prompt_templates,
    test_model_connection,
    toggle_compact_archive,
    trigger_case_import,
    trigger_client_import,
    trigger_oa_filing,
    unified_generate,
    update_case,
    update_case_assignment,
    update_case_log,
    update_case_number,
    update_case_party,
    update_client,
    update_contact,
    update_contract,
    update_contract_lawyers,
    update_credential,
    update_document_template,
    update_folder_template,
    update_grant,
    update_lawfirm,
    update_lawyer,
    update_mapping,
    update_message_source,
    update_payment,
    update_placeholder,
    update_property_clue,
    update_recording,
    update_reminder,
    update_screenshot,
    update_supplementary_agreement,
    update_system_configs,
    update_team,
    update_workflow_template,
    upload_contract_for_review,
    upload_invoices,
    validate_folder_structure,
    validate_id_card,
    warm_up_cache,
    web_search,
)

# 条件导入：网上立案
try:
    from mcp_server.tools import execute_court_filing, get_court_filing_case_info, get_court_filing_session

    _HAS_FILING = True
except ImportError:
    _HAS_FILING = False

# 条件导入：诉讼保全
try:
    from mcp_server.tools import (
        bind_guarantee_quote,
        delete_guarantee_binding,
        delete_guarantee_quote,
        ensure_guarantee_quote,
        execute_guarantee,
        get_guarantee_case_info,
        get_guarantee_session,
        retry_guarantee_quote,
    )

    _HAS_GUARANTEE = True
except ImportError:
    _HAS_GUARANTEE = False

# 条件导入：财产保全询价
try:
    from mcp_server.tools import (
        create_preservation_quote,
        execute_preservation_quote,
        get_preservation_quote,
        list_preservation_quotes,
        retry_preservation_quote,
    )

    _HAS_QUOTE = True
except ImportError:
    _HAS_QUOTE = False

mcp = MCPServer("法穿SI Copilot")

# ---------------------------------------------------------------------------
# 统一注册口:从审批分层权威表(apps.agent.services.approval)推导 MCP
# ToolAnnotations——与审批双表(Python/TS)共源,不另立第三份口径。
# 官方参考 server 均设 annotations;客户端(pi/其他 MCP host)可用
# readOnlyHint 做只读徽标/免审批策略,destructiveHint 标销毁型操作。
# payload 纪律:只有「读」与「销毁」带标注,普通写工具不带(默认即非只读
# 非销毁,省 ~45B/工具 × 409 的 tools/list 体积)。
# ---------------------------------------------------------------------------
_DESTRUCTIVE_PREFIXES = ("delete_", "clear_", "reset_", "cleanup_")


def _tool_annotations(name: str) -> ToolAnnotations | None:
    """按工具名推导 MCP 行为提示。销毁前缀或 HIGH/CRITICAL(递交/外发/
    归档确认等不可逆外部动作)标 destructive;LOW(读/无副作用计算)标
    readOnly;MEDIUM 普通写不带标注(默认即非只读非销毁,省 payload)。"""
    level = classify_risk(name)
    if name.startswith(_DESTRUCTIVE_PREFIXES) or level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return ToolAnnotations(destructive_hint=True)
    if level == RiskLevel.LOW:
        return ToolAnnotations(read_only_hint=True)
    return None


def _t(func: Any) -> Any:
    """409 个工具的统一注册装饰器(替代裸 ``mcp.tool()``)。"""
    return mcp.tool(annotations=_tool_annotations(getattr(func, "__name__", "")))(func)


# 案件
_t(list_cases)
_t(search_cases)
_t(get_case)
_t(create_case)
_t(update_case)
_t(delete_case)
_t(create_full_case)

# 案件当事人
_t(list_case_parties)
_t(add_case_party)
_t(get_case_party)
_t(update_case_party)
_t(delete_case_party)

# 案件进展日志
_t(list_case_logs)
_t(create_case_log)
_t(get_case_log)
_t(update_case_log)
_t(delete_case_log)

# 案号
_t(list_case_numbers)
_t(create_case_number)
_t(get_case_number)
_t(update_case_number)
_t(delete_case_number)

# 律师指派
_t(list_case_assignments)
_t(assign_lawyer)
_t(get_case_assignment)
_t(update_case_assignment)
_t(delete_case_assignment)

# 案件访问权限
_t(list_grants)
_t(create_grant)
_t(get_grant)
_t(update_grant)
_t(delete_grant)

# 案由/法院数据
_t(list_causes_data)
_t(list_causes_tree)
_t(get_cause)
_t(list_courts_data)

# 诉讼费
_t(calculate_litigation_fee)

# 案件材料
_t(list_bind_candidates)
_t(bind_materials)
_t(save_group_order)
_t(rename_material_group)
_t(delete_material)
_t(delete_all_materials)

# 案件文件夹扫描
_t(start_folder_scan)
_t(list_scan_subfolders)
_t(get_scan_status)
_t(create_scan_stage)

# 案件文件夹绑定
_t(create_case_folder_binding)
_t(get_case_folder_binding)
_t(delete_case_folder_binding)
_t(get_contract_folder_path)
_t(browse_case_folders)
_t(list_case_cloud_storage_accounts)

# 案件模板绑定
_t(list_template_bindings)
_t(create_template_binding)
_t(delete_template_binding)
_t(list_available_templates)
_t(generate_case_template)
_t(unified_generate)

# 客户
_t(list_clients)
_t(get_client)
_t(create_client)
_t(parse_client_text)
_t(update_client)
_t(delete_client)
_t(list_clients_with_docs)
_t(enterprise_search)
_t(enterprise_prefill)
_t(get_identity_doc)
_t(delete_identity_doc)
_t(get_identity_doc_task)
_t(submit_identity_doc_recognition)
_t(merge_id_card_manual)
_t(validate_id_card)
_t(check_oa_credential)

# 客户财产线索
_t(list_property_clues)
_t(create_property_clue)
_t(get_property_clue)
_t(update_property_clue)
_t(delete_property_clue)
_t(get_property_clue_content_template)

# 联系人
_t(list_contacts)
_t(create_contact)
_t(search_contacts)
_t(get_contact)
_t(update_contact)
_t(delete_contact)

# 合同
_t(list_contracts)
_t(get_contract)
_t(create_contract)
_t(create_contract_with_cases)
_t(update_contract)
_t(delete_contract)
_t(update_contract_lawyers)
_t(get_contract_all_parties)

# 合同收款
_t(create_payment)
_t(update_payment)
_t(delete_payment)

# 补充协议
_t(list_supplementary_agreements)
_t(get_supplementary_agreement)
_t(create_supplementary_agreement)
_t(update_supplementary_agreement)
_t(delete_supplementary_agreement)

# 合同文件夹
_t(create_folder_binding)
_t(get_folder_binding)
_t(delete_folder_binding)
_t(browse_folders)
_t(list_cloud_storage_accounts)

# 合同归档
_t(learn_archive_rules)
_t(get_archive_checklist)
_t(download_archive_item)
_t(generate_archive_folder)
_t(toggle_compact_archive)
_t(sync_case_materials)
_t(reset_and_resync_case_materials)
_t(scale_to_a4)
_t(confirm_archive)
_t(delete_archive_material)
_t(reorder_archive_materials)
_t(move_archive_material)
_t(clear_all_archive_materials)

# 合同文件夹扫描
_t(start_contract_scan)
_t(list_contract_scan_subfolders)
_t(get_latest_contract_scan)
_t(get_contract_scan_status)
_t(confirm_contract_scan)

# 提醒
_t(list_all_reminders)
_t(get_reminder)
_t(create_new_reminder)
_t(update_reminder)
_t(delete_reminder)
_t(list_reminder_types)
_t(parse_reminders_from_text)
_t(get_target_options)

# 财务
_t(list_payments)
_t(get_finance_stats)

# 组织架构 - 律师
_t(list_lawyers)
_t(get_lawyer)
_t(create_lawyer)
_t(update_lawyer)
_t(delete_lawyer)

# 组织架构 - 律所
_t(list_lawfirms)
_t(get_lawfirm)
_t(create_lawfirm)
_t(update_lawfirm)
_t(delete_lawfirm)

# 组织架构 - 团队
_t(list_teams)
_t(get_team)
_t(create_team)
_t(update_team)
_t(delete_team)

# 组织架构 - 账号凭证
_t(list_credentials)
_t(get_credential)
_t(create_credential)
_t(update_credential)
_t(delete_credential)

# OA 立案
_t(list_oa_configs)
_t(trigger_oa_filing)
_t(get_filing_status)

# 企业数据
_t(list_enterprise_providers)
_t(search_companies)
_t(get_company_profile)
_t(get_company_risks)
_t(get_company_shareholders)
_t(get_company_personnel)
_t(get_person_profile)
_t(search_bidding_info)

# 类案检索
_t(create_research_task)
_t(capability_search)
_t(get_research_task)
_t(list_research_results)
_t(download_research_result)
_t(download_all_research_results)
_t(check_law_references)

# 自动化 - 法院短信
_t(submit_court_sms)
_t(list_court_sms)
_t(get_court_sms_detail)
_t(assign_sms_case)
_t(retry_sms_processing)
_t(delete_court_sms)
_t(download_sms_documents)
_t(download_sms_document)

# 自动化 - 财产保全询价 (需 plugins/court_automation)
if _HAS_QUOTE:
    _t(create_preservation_quote)
    _t(list_preservation_quotes)
    _t(get_preservation_quote)
    _t(execute_preservation_quote)
    _t(retry_preservation_quote)

# 自动化 - 文书送达

# 自动化 - 验证码
_t(get_captcha_image)
_t(submit_captcha_answer)

# 自动化 - 自动命名
_t(auto_namer_process_by_path)

# 自动化 - 网上立案 (需 plugins/court_automation)
if _HAS_FILING:
    _t(get_court_filing_case_info)
    _t(get_court_filing_session)
    _t(execute_court_filing)

# 自动化 - 诉讼保全 (需 plugins/court_automation)
if _HAS_GUARANTEE:
    _t(get_guarantee_case_info)
    _t(get_guarantee_session)
    _t(execute_guarantee)
    _t(ensure_guarantee_quote)
    _t(bind_guarantee_quote)
    _t(delete_guarantee_quote)
    _t(retry_guarantee_quote)
    _t(delete_guarantee_binding)

# 自动化 - 性能监控
_t(health_check)
_t(get_performance_metrics)
_t(get_statistics_report)
_t(get_resource_usage)
_t(get_cache_statistics)
_t(optimize_concurrency)
_t(warm_up_cache)
_t(clear_cache)
_t(reset_performance_metrics)
_t(cleanup_resources)

# 自动化 - 文档处理器
_t(process_document)
_t(process_document_by_path)

# 自动化 - 主 API
_t(get_automation_config)
_t(get_automation_status)

# PDF 拆解
_t(create_pdf_split_job)
_t(get_pdf_split_job)
_t(confirm_pdf_split)
_t(cancel_pdf_split)
_t(download_pdf_split_result)
_t(get_pdf_split_page_preview)
_t(download_pdf_split_raw)

# OA 导入
_t(trigger_client_import)
_t(get_client_import_session)
_t(batch_create_clients)
_t(trigger_case_import)
_t(get_case_import_session)
_t(get_case_import_preview)
_t(execute_case_import)
_t(batch_create_cases)

# 要素式转换
_t(list_doc_convert_types)
_t(convert_document)

# 文档转换
_t(get_conversion_progress)
_t(cancel_conversion_job)
_t(download_converted_files)
_t(delete_conversion_job)
_t(doc_converter_health_check)
_t(save_to_directory)

# 发票识别
_t(quick_recognize_invoice)
_t(upload_invoices)
_t(get_invoice_task_status)
_t(download_invoices)

# 聊天记录取证
_t(create_project)
_t(list_projects)
_t(list_recordings)
_t(list_screenshots)
_t(create_export)
_t(get_export_task)
_t(get_export_types)
_t(get_export_statuses)
_t(download_export)
_t(get_recording)
_t(update_recording)
_t(delete_recording)
_t(extract_recording)
_t(cancel_extract_recording)
_t(reset_extract_recording)
_t(update_screenshot)
_t(reorder_screenshots)

# 合同审查
_t(upload_contract_for_review)
_t(get_review_status)
_t(get_review_models)
_t(confirm_party)
_t(download_review_result)
_t(download_review_original)
_t(normalize_contract_format)
_t(download_normalized_result)

# 文书生产 - 基础查询
_t(list_document_templates)
_t(get_document_template)
_t(create_document_template)
_t(list_folder_templates)
_t(list_placeholders)
_t(preview_placeholders)
_t(preview_contract_context)
_t(download_contract_document)
_t(download_contract_folder)

# 文书生产 - 模板操作
_t(update_document_template)
_t(delete_document_template)
_t(extract_template_placeholders)
_t(get_undefined_placeholders)
_t(list_template_library_files)

# 文件夹模板操作
_t(get_folder_template)
_t(create_folder_template)
_t(update_folder_template)
_t(delete_folder_template)
_t(validate_folder_structure)

# 替换词操作
_t(get_placeholder)
_t(get_placeholder_by_key)
_t(create_placeholder)
_t(update_placeholder)
_t(delete_placeholder)

# 文档生成操作
_t(preview_supplementary_agreement_context)
_t(preview_archive_context)
_t(get_archive_overrides)
_t(save_archive_overrides)
_t(delete_archive_overrides)
_t(download_supplementary_agreement)

# 诉讼文书生成
_t(generate_complaint)
_t(generate_defense)
_t(preview_litigation_context)
_t(download_litigation_document)

# 授权委托材料
_t(download_authority_letter)
_t(download_legal_rep_certificate)
_t(download_power_of_attorney_combined)
_t(download_authorization_package)
_t(download_power_of_attorney)

# 财产保全材料
_t(download_preservation_application)
_t(download_delay_delivery_application)
_t(download_full_preservation_package)

# 外部模板
_t(analyze_template)
_t(confirm_mappings)
_t(preview_fill)
_t(match_templates)
_t(get_custom_fields)
_t(get_fill_history)
_t(get_statistics)
_t(get_preview_html)
_t(list_mappings)
_t(create_mapping)
_t(update_mapping)
_t(delete_mapping)

# 证据管理
_t(reorder_evidence_items)

# LPR 利率
_t(list_lpr_rates)
_t(get_latest_lpr_rate)
_t(calculate_interest)
_t(sync_lpr_rates)
_t(get_lpr_sync_status)

# 房贷摊销 / 逾期违约债权（银行诉讼）
_t(mortgage_amortize)
_t(mortgage_default_calculate)

# 图片旋转
_t(extract_pdf_pages)
_t(detect_orientation)
_t(suggest_rename)
_t(detect_single_page_orientation)
_t(export_rotated_pdf)
_t(export_rotated_images)

# 收件箱 - 消息
_t(list_inbox_messages)
_t(get_inbox_message)
_t(rename_inbox_attachment)
_t(download_inbox_attachment)
_t(preview_inbox_attachment)

# 收件箱 - 来源
_t(list_message_sources)
_t(get_message_source)
_t(create_message_source)
_t(update_message_source)
_t(delete_message_source)
_t(sync_message_source)
_t(sync_all_message_sources)

# 核心 - LLM 服务
_t(chat_with_context)
_t(get_conversation_history)
_t(sync_prompt_templates)
_t(list_available_models)
_t(test_model_connection)

# 核心 - 系统配置
_t(list_system_configs)
_t(update_system_configs)
_t(create_system_config)
_t(patch_system_config)
_t(delete_system_config)

# 核心 - 仪表盘
_t(get_dashboard_stats)

# 核心 - 全局搜索
_t(global_search)

# 核心 - 任务队列
_t(list_queued_tasks)
_t(list_completed_tasks)
_t(list_failed_tasks)
_t(list_scheduled_tasks)
_t(delete_task)
_t(delete_schedule)
_t(resubmit_task)

# 核心 - POI 文档生成

# 网络搜索
_t(web_search)
_t(fetch_url)


# 工作流引擎
# _workflow_tool 统一包装 workflow 的 MCP 注册,做两件事:
# 1. 参数剥离:user/org_access/perm_open_access 是 REST 直调专用(ContextVar
#    身份重建在函数内做),不剥离则进 MCP inputSchema,模型看到无法构造的
#    object 参数,且乱传时会绕过身份重建。
# 2. 业务异常翻译:workflow 工具直接 ORM,访问校验抛 apps.core 的
#    BusinessException(NotFoundError/PermissionDenied 等)——不是 ToolError
#    子类,SDK 会包成 UnexpectedToolError 黑盒(模型只看到 "Error executing
#    tool X",连「案件不存在」还是「无权限」都分不清,无法自纠)。这里翻译
#    成 ToolError,detail(中文,本来就是给用户看的)直达模型。
def _workflow_tool(fn: Any) -> Any:
    import inspect
    from functools import wraps

    from django.core.exceptions import ObjectDoesNotExist
    from mcp.server.mcpserver.exceptions import ToolError

    from apps.core.exceptions.common import BusinessException

    drop = {"user", "org_access", "perm_open_access"}

    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except BusinessException as exc:
                raise ToolError(str(exc) or exc.__class__.__name__) from exc
            except ObjectDoesNotExist as exc:
                # Django 原生「查无此物」同样是预期内失败(模型传错 id/slug),
                # 不翻译则黑盒——E2E 实测 start_workflow 坏 slug 只有半句报错
                raise ToolError(f"对象不存在: {exc}") from exc

    else:

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except BusinessException as exc:
                raise ToolError(str(exc) or exc.__class__.__name__) from exc
            except ObjectDoesNotExist as exc:
                raise ToolError(f"对象不存在: {exc}") from exc

    sig = inspect.signature(fn)
    wrapper.__signature__ = sig.replace(  # type: ignore[attr-defined]
        parameters=[p for p in sig.parameters.values() if p.name not in drop]
    )
    return wrapper


_t(_workflow_tool(start_workflow))
_t(_workflow_tool(list_workflows))
_t(_workflow_tool(get_workflow_detail))
_t(_workflow_tool(approve_workflow_step))
_t(_workflow_tool(cancel_workflow))
# 工作流引擎 · 模板管理与注册表(2026-10-25 补注册;此前实现完整但从未暴露,
# 注册完整性门禁 test_tool_registration 抓出)。模板写入/删除/复制仅管理员
# (workflow_tools._require_admin,与 REST ensure_admin_request 同口径);
# run 删除复用 _mcp_guard_run_access 案件访问校验。
_t(_workflow_tool(delete_workflow_run))
_t(_workflow_tool(get_step_registry))
_t(_workflow_tool(get_step_registry_flat))
_t(_workflow_tool(create_workflow_template))
_t(_workflow_tool(update_workflow_template))
_t(_workflow_tool(list_workflow_templates))
_t(_workflow_tool(get_workflow_template))
_t(_workflow_tool(delete_workflow_template))
_t(_workflow_tool(duplicate_workflow_template))
_t(_workflow_tool(start_workflow_from_steps))

# ===== 新增能力（身份 / 期限聚合 / 文档正文 / 任务统一状态）=====
# 身份与时间：模型自述「我是谁、现在几点」的唯一来源
_t(get_current_user)
_t(get_server_time)

# 专项技能指引：场景化操作说明按需供给（AGENTS.md 只保留路由，省上下文）
_t(get_agent_skill)

# 对话附件：服务端读文件提取正文（base64 不进模型上下文）
_t(read_agent_attachment)
# 绑定文件夹引用：拖拽引用型，读原文件（不复制，路径即归属）
_t(list_folder_files)
_t(read_folder_file)

# 期限聚合：跨案件/合同/日志汇总到期事项
_t(list_upcoming_deadlines)
_t(list_reminders_by_target)
_t(get_reminder_calendar)
_t(complete_reminders)
_t(delete_reminders)

# 文档正文（材料可检索的底座）
_t(extract_document_text)
_t(parse_document)
_t(get_document_parsing_task)
_t(list_document_parsing_records)

# 文书批量生成
_t(fill_templates)

# 文件夹浏览
_t(list_case_folder_entries)
_t(list_contract_folder_entries)

# 客户全景与合同当事人
_t(get_client_related_items)
_t(add_contract_party)
_t(remove_contract_party)

# 异步任务统一状态
_t(get_async_task_status)
_t(list_doc_converter_jobs)
_t(create_doc_converter_job)
_t(list_litigation_sessions)
_t(list_pending_court_document_tasks)
