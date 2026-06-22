"""MCP Server 主入口 - 法穿AI Copilot"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_server.tools import (
    add_case_party,
    ai_ollama,
    analyze_template,
    assign_lawyer,
    assign_sms_case,
    auto_namer_process,
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
    capability_search,
    check_law_references,
    check_oa_credential,
    chat_with_context,
    cleanup_resources,
    clear_all_archive_materials,
    clear_cache,
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
    create_document_template,
    create_export,
    create_folder_binding,
    create_folder_template,
    create_full_case,
    create_grant,
    create_lawfirm,
    create_lawyer,
    create_mapping,
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
    create_message_source,
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
    delete_conversion_job,
    delete_contract,
    delete_credential,
    delete_court_sms,
    delete_document_template,
    delete_folder_binding,
    delete_folder_template,
    delete_grant,
    delete_identity_doc,
    delete_lawfirm,
    delete_lawyer,
    delete_mapping,
    delete_material,
    delete_payment,
    delete_placeholder,
    delete_property_clue,
    delete_recording,
    delete_reminder,
    delete_schedule,
    delete_screenshot,
    delete_supplementary_agreement,
    delete_system_config,
    delete_task,
    delete_team,
    delete_template_binding,
    delete_message_source,
    detect_orientation,
    detect_single_page_orientation,
    doc_converter_health_check,
    download_all_research_results,
    download_archive_item,
    download_authorization_package,
    download_authority_letter,
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
    enterprise_prefill,
    enterprise_search,
    execute_case_import,
    export_rotated_images,
    export_rotated_pdf,
    extract_pdf_pages,
    extract_recording,
    extract_template_placeholders,
    generate_archive_folder,
    generate_case_template,
    generate_complaint,
    generate_defense,
    generate_poi_complaint,
    generate_report,
    get_archive_checklist,
    get_archive_overrides,
    get_automation_config,
    get_automation_status,
    get_captcha_image,
    get_case,
    get_case_assignment,
    get_case_folder_binding,
    get_case_import_preview,
    get_case_import_session,
    get_case_log,
    get_case_number,
    get_case_party,
    get_cache_statistics,
    get_cause,
    get_client,
    get_client_import_session,
    get_company_personnel,
    get_company_profile,
    get_company_risks,
    get_company_shareholders,
    get_contact,
    get_conversation_history,
    get_contract,
    get_contract_all_parties,
    get_contract_folder_path,
    get_contract_scan_status,
    get_conversion_progress,
    get_credential,
    get_grant,
    get_court_sms_detail,
    get_custom_fields,
    get_dashboard_stats,
    get_document_template,
    get_export_statuses,
    get_export_task,
    get_export_types,
    get_fill_history,
    get_filing_status,
    get_folder_binding,
    get_folder_template,
    get_finance_stats,
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
    get_research_task,
    get_resource_usage,
    get_review_models,
    get_review_status,
    get_scan_status,
    get_statistics,
    get_statistics_report,
    get_supplementary_agreement,
    get_target_options,
    get_team,
    get_undefined_placeholders,
    global_search,
    health_check,
    learn_archive_rules,
    list_all_reminders,
    list_available_models,
    list_available_templates,
    list_bind_candidates,
    list_case_assignments,
    list_case_cloud_storage_accounts,
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
    list_contracts,
    list_contract_scan_subfolders,
    list_court_sms,
    list_courts_data,
    list_credentials,
    list_doc_convert_types,
    list_document_templates,
    list_enterprise_providers,
    list_failed_tasks,
    list_folder_templates,
    list_grants,
    list_inbox_messages,
    list_lawfirms,
    list_lawyers,
    list_lpr_rates,
    list_mappings,
    list_message_sources,
    list_oa_configs,
    list_payments,
    list_placeholders,
    list_projects,
    list_property_clues,
    list_queued_tasks,
    list_recordings,
    list_reminder_types,
    list_research_results,
    list_scan_subfolders,
    list_scheduled_tasks,
    list_screenshots,
    list_supplementary_agreements,
    list_system_configs,
    list_teams,
    list_template_bindings,
    list_template_library_files,
    match_templates,
    merge_id_card_manual,
    move_archive_material,
    normalize_contract_format,
    optimize_concurrency,
    parse_client_text,
    parse_reminders_from_text,
    patch_system_config,
    poi_health,
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
    upload_contract_for_review,
    upload_invoices,
    validate_folder_structure,
    validate_id_card,
    warm_up_cache,
    web_search,
    start_workflow,
    list_workflows,
    get_workflow_detail,
    approve_workflow_step,
    cancel_workflow,
)

# 条件导入：网上立案
try:
    from mcp_server.tools import (
        execute_court_filing,
        get_court_filing_case_info,
        get_court_filing_session,
    )
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

mcp = FastMCP("法穿AI Copilot")

# 案件
mcp.tool()(list_cases)
mcp.tool()(search_cases)
mcp.tool()(get_case)
mcp.tool()(create_case)
mcp.tool()(update_case)
mcp.tool()(delete_case)
mcp.tool()(create_full_case)

# 案件当事人
mcp.tool()(list_case_parties)
mcp.tool()(add_case_party)
mcp.tool()(get_case_party)
mcp.tool()(update_case_party)
mcp.tool()(delete_case_party)

# 案件进展日志
mcp.tool()(list_case_logs)
mcp.tool()(create_case_log)
mcp.tool()(get_case_log)
mcp.tool()(update_case_log)
mcp.tool()(delete_case_log)

# 案号
mcp.tool()(list_case_numbers)
mcp.tool()(create_case_number)
mcp.tool()(get_case_number)
mcp.tool()(update_case_number)
mcp.tool()(delete_case_number)

# 律师指派
mcp.tool()(list_case_assignments)
mcp.tool()(assign_lawyer)
mcp.tool()(get_case_assignment)
mcp.tool()(update_case_assignment)
mcp.tool()(delete_case_assignment)

# 案件访问权限
mcp.tool()(list_grants)
mcp.tool()(create_grant)
mcp.tool()(get_grant)
mcp.tool()(update_grant)
mcp.tool()(delete_grant)

# 案由/法院数据
mcp.tool()(list_causes_data)
mcp.tool()(list_causes_tree)
mcp.tool()(get_cause)
mcp.tool()(list_courts_data)

# 诉讼费
mcp.tool()(calculate_litigation_fee)

# 案件材料
mcp.tool()(list_bind_candidates)
mcp.tool()(bind_materials)
mcp.tool()(save_group_order)
mcp.tool()(rename_material_group)
mcp.tool()(delete_material)
mcp.tool()(delete_all_materials)

# 案件文件夹扫描
mcp.tool()(start_folder_scan)
mcp.tool()(list_scan_subfolders)
mcp.tool()(get_scan_status)
mcp.tool()(create_scan_stage)

# 案件文件夹绑定
mcp.tool()(create_case_folder_binding)
mcp.tool()(get_case_folder_binding)
mcp.tool()(delete_case_folder_binding)
mcp.tool()(get_contract_folder_path)
mcp.tool()(browse_case_folders)
mcp.tool()(list_case_cloud_storage_accounts)

# 案件模板绑定
mcp.tool()(list_template_bindings)
mcp.tool()(create_template_binding)
mcp.tool()(delete_template_binding)
mcp.tool()(list_available_templates)
mcp.tool()(generate_case_template)
mcp.tool()(unified_generate)

# 客户
mcp.tool()(list_clients)
mcp.tool()(get_client)
mcp.tool()(create_client)
mcp.tool()(parse_client_text)
mcp.tool()(update_client)
mcp.tool()(delete_client)
mcp.tool()(list_clients_with_docs)
mcp.tool()(enterprise_search)
mcp.tool()(enterprise_prefill)
mcp.tool()(get_identity_doc)
mcp.tool()(delete_identity_doc)
mcp.tool()(get_identity_doc_task)
mcp.tool()(submit_identity_doc_recognition)
mcp.tool()(merge_id_card_manual)
mcp.tool()(validate_id_card)
mcp.tool()(check_oa_credential)

# 客户财产线索
mcp.tool()(list_property_clues)
mcp.tool()(create_property_clue)
mcp.tool()(get_property_clue)
mcp.tool()(update_property_clue)
mcp.tool()(delete_property_clue)
mcp.tool()(get_property_clue_content_template)

# 联系人
mcp.tool()(list_contacts)
mcp.tool()(create_contact)
mcp.tool()(search_contacts)
mcp.tool()(get_contact)
mcp.tool()(update_contact)
mcp.tool()(delete_contact)

# 合同
mcp.tool()(list_contracts)
mcp.tool()(get_contract)
mcp.tool()(create_contract)
mcp.tool()(create_contract_with_cases)
mcp.tool()(update_contract)
mcp.tool()(delete_contract)
mcp.tool()(update_contract_lawyers)
mcp.tool()(get_contract_all_parties)

# 合同收款
mcp.tool()(create_payment)
mcp.tool()(update_payment)
mcp.tool()(delete_payment)

# 补充协议
mcp.tool()(list_supplementary_agreements)
mcp.tool()(get_supplementary_agreement)
mcp.tool()(create_supplementary_agreement)
mcp.tool()(update_supplementary_agreement)
mcp.tool()(delete_supplementary_agreement)

# 合同文件夹
mcp.tool()(create_folder_binding)
mcp.tool()(get_folder_binding)
mcp.tool()(delete_folder_binding)
mcp.tool()(browse_folders)
mcp.tool()(list_cloud_storage_accounts)

# 合同归档
mcp.tool()(learn_archive_rules)
mcp.tool()(get_archive_checklist)
mcp.tool()(download_archive_item)
mcp.tool()(generate_archive_folder)
mcp.tool()(toggle_compact_archive)
mcp.tool()(sync_case_materials)
mcp.tool()(reset_and_resync_case_materials)
mcp.tool()(scale_to_a4)
mcp.tool()(confirm_archive)
mcp.tool()(delete_archive_material)
mcp.tool()(reorder_archive_materials)
mcp.tool()(move_archive_material)
mcp.tool()(clear_all_archive_materials)

# 合同文件夹扫描
mcp.tool()(start_contract_scan)
mcp.tool()(list_contract_scan_subfolders)
mcp.tool()(get_latest_contract_scan)
mcp.tool()(get_contract_scan_status)
mcp.tool()(confirm_contract_scan)

# 提醒
mcp.tool()(list_all_reminders)
mcp.tool()(get_reminder)
mcp.tool()(create_new_reminder)
mcp.tool()(update_reminder)
mcp.tool()(delete_reminder)
mcp.tool()(list_reminder_types)
mcp.tool()(parse_reminders_from_text)
mcp.tool()(get_target_options)

# 财务
mcp.tool()(list_payments)
mcp.tool()(get_finance_stats)

# 组织架构 - 律师
mcp.tool()(list_lawyers)
mcp.tool()(get_lawyer)
mcp.tool()(create_lawyer)
mcp.tool()(update_lawyer)
mcp.tool()(delete_lawyer)

# 组织架构 - 律所
mcp.tool()(list_lawfirms)
mcp.tool()(get_lawfirm)
mcp.tool()(create_lawfirm)
mcp.tool()(update_lawfirm)
mcp.tool()(delete_lawfirm)

# 组织架构 - 团队
mcp.tool()(list_teams)
mcp.tool()(get_team)
mcp.tool()(create_team)
mcp.tool()(update_team)
mcp.tool()(delete_team)

# 组织架构 - 账号凭证
mcp.tool()(list_credentials)
mcp.tool()(get_credential)
mcp.tool()(create_credential)
mcp.tool()(update_credential)
mcp.tool()(delete_credential)

# OA 立案
mcp.tool()(list_oa_configs)
mcp.tool()(trigger_oa_filing)
mcp.tool()(get_filing_status)

# 企业数据
mcp.tool()(list_enterprise_providers)
mcp.tool()(search_companies)
mcp.tool()(get_company_profile)
mcp.tool()(get_company_risks)
mcp.tool()(get_company_shareholders)
mcp.tool()(get_company_personnel)
mcp.tool()(get_person_profile)
mcp.tool()(search_bidding_info)

# 类案检索
mcp.tool()(create_research_task)
mcp.tool()(capability_search)
mcp.tool()(get_research_task)
mcp.tool()(list_research_results)
mcp.tool()(download_research_result)
mcp.tool()(download_all_research_results)
mcp.tool()(check_law_references)

# 自动化 - 法院短信
mcp.tool()(submit_court_sms)
mcp.tool()(list_court_sms)
mcp.tool()(get_court_sms_detail)
mcp.tool()(assign_sms_case)
mcp.tool()(retry_sms_processing)
mcp.tool()(delete_court_sms)
mcp.tool()(download_sms_documents)
mcp.tool()(download_sms_document)

# 自动化 - 财产保全询价 (需 plugins/court_automation)
if _HAS_QUOTE:
    mcp.tool()(create_preservation_quote)
    mcp.tool()(list_preservation_quotes)
    mcp.tool()(get_preservation_quote)
    mcp.tool()(execute_preservation_quote)
    mcp.tool()(retry_preservation_quote)

# 自动化 - 文书送达

# 自动化 - 验证码
mcp.tool()(get_captcha_image)
mcp.tool()(submit_captcha_answer)

# 自动化 - 自动命名
mcp.tool()(auto_namer_process)
mcp.tool()(auto_namer_process_by_path)

# 自动化 - 网上立案 (需 plugins/court_automation)
if _HAS_FILING:
    mcp.tool()(get_court_filing_case_info)
    mcp.tool()(get_court_filing_session)
    mcp.tool()(execute_court_filing)

# 自动化 - 诉讼保全 (需 plugins/court_automation)
if _HAS_GUARANTEE:
    mcp.tool()(get_guarantee_case_info)
    mcp.tool()(get_guarantee_session)
    mcp.tool()(execute_guarantee)
    mcp.tool()(ensure_guarantee_quote)
    mcp.tool()(bind_guarantee_quote)
    mcp.tool()(delete_guarantee_quote)
    mcp.tool()(retry_guarantee_quote)
    mcp.tool()(delete_guarantee_binding)

# 自动化 - 性能监控
mcp.tool()(health_check)
mcp.tool()(get_performance_metrics)
mcp.tool()(get_statistics_report)
mcp.tool()(get_resource_usage)
mcp.tool()(get_cache_statistics)
mcp.tool()(optimize_concurrency)
mcp.tool()(warm_up_cache)
mcp.tool()(clear_cache)
mcp.tool()(reset_performance_metrics)
mcp.tool()(cleanup_resources)

# 自动化 - 文档处理器
mcp.tool()(process_document)
mcp.tool()(process_document_by_path)

# 自动化 - 主 API
mcp.tool()(ai_ollama)
mcp.tool()(get_automation_config)
mcp.tool()(get_automation_status)

# PDF 拆解
mcp.tool()(create_pdf_split_job)
mcp.tool()(get_pdf_split_job)
mcp.tool()(confirm_pdf_split)
mcp.tool()(cancel_pdf_split)
mcp.tool()(download_pdf_split_result)
mcp.tool()(get_pdf_split_page_preview)
mcp.tool()(download_pdf_split_raw)

# OA 导入
mcp.tool()(trigger_client_import)
mcp.tool()(get_client_import_session)
mcp.tool()(batch_create_clients)
mcp.tool()(trigger_case_import)
mcp.tool()(get_case_import_session)
mcp.tool()(get_case_import_preview)
mcp.tool()(execute_case_import)
mcp.tool()(batch_create_cases)

# 要素式转换
mcp.tool()(list_doc_convert_types)
mcp.tool()(convert_document)

# 文档转换
mcp.tool()(get_conversion_progress)
mcp.tool()(cancel_conversion_job)
mcp.tool()(download_converted_files)
mcp.tool()(delete_conversion_job)
mcp.tool()(doc_converter_health_check)
mcp.tool()(save_to_directory)

# 发票识别
mcp.tool()(quick_recognize_invoice)
mcp.tool()(upload_invoices)
mcp.tool()(get_invoice_task_status)
mcp.tool()(download_invoices)

# 聊天记录取证
mcp.tool()(create_project)
mcp.tool()(list_projects)
mcp.tool()(list_recordings)
mcp.tool()(list_screenshots)
mcp.tool()(create_export)
mcp.tool()(get_export_task)
mcp.tool()(get_export_types)
mcp.tool()(get_export_statuses)
mcp.tool()(download_export)
mcp.tool()(get_recording)
mcp.tool()(update_recording)
mcp.tool()(delete_recording)
mcp.tool()(extract_recording)
mcp.tool()(cancel_extract_recording)
mcp.tool()(reset_extract_recording)
mcp.tool()(update_screenshot)
mcp.tool()(delete_screenshot)
mcp.tool()(reorder_screenshots)

# 合同审查
mcp.tool()(upload_contract_for_review)
mcp.tool()(get_review_status)
mcp.tool()(get_review_models)
mcp.tool()(confirm_party)
mcp.tool()(download_review_result)
mcp.tool()(download_review_original)
mcp.tool()(normalize_contract_format)
mcp.tool()(download_normalized_result)

# 文书生产 - 基础查询
mcp.tool()(list_document_templates)
mcp.tool()(get_document_template)
mcp.tool()(create_document_template)
mcp.tool()(list_folder_templates)
mcp.tool()(list_placeholders)
mcp.tool()(preview_placeholders)
mcp.tool()(preview_contract_context)
mcp.tool()(download_contract_document)
mcp.tool()(download_contract_folder)

# 文书生产 - 模板操作
mcp.tool()(update_document_template)
mcp.tool()(delete_document_template)
mcp.tool()(extract_template_placeholders)
mcp.tool()(get_undefined_placeholders)
mcp.tool()(list_template_library_files)

# 文件夹模板操作
mcp.tool()(get_folder_template)
mcp.tool()(create_folder_template)
mcp.tool()(update_folder_template)
mcp.tool()(delete_folder_template)
mcp.tool()(validate_folder_structure)

# 替换词操作
mcp.tool()(get_placeholder)
mcp.tool()(get_placeholder_by_key)
mcp.tool()(create_placeholder)
mcp.tool()(update_placeholder)
mcp.tool()(delete_placeholder)

# 文档生成操作
mcp.tool()(preview_supplementary_agreement_context)
mcp.tool()(preview_archive_context)
mcp.tool()(get_archive_overrides)
mcp.tool()(save_archive_overrides)
mcp.tool()(delete_archive_overrides)
mcp.tool()(download_supplementary_agreement)

# 诉讼文书生成
mcp.tool()(generate_complaint)
mcp.tool()(generate_defense)
mcp.tool()(preview_litigation_context)
mcp.tool()(download_litigation_document)

# 授权委托材料
mcp.tool()(download_authority_letter)
mcp.tool()(download_legal_rep_certificate)
mcp.tool()(download_power_of_attorney_combined)
mcp.tool()(download_authorization_package)
mcp.tool()(download_power_of_attorney)

# 财产保全材料
mcp.tool()(download_preservation_application)
mcp.tool()(download_delay_delivery_application)
mcp.tool()(download_full_preservation_package)

# 外部模板
mcp.tool()(analyze_template)
mcp.tool()(confirm_mappings)
mcp.tool()(preview_fill)
mcp.tool()(match_templates)
mcp.tool()(get_custom_fields)
mcp.tool()(get_fill_history)
mcp.tool()(get_statistics)
mcp.tool()(get_preview_html)
mcp.tool()(list_mappings)
mcp.tool()(create_mapping)
mcp.tool()(update_mapping)
mcp.tool()(delete_mapping)

# 证据管理
mcp.tool()(reorder_evidence_items)

# LPR 利率
mcp.tool()(list_lpr_rates)
mcp.tool()(get_latest_lpr_rate)
mcp.tool()(calculate_interest)
mcp.tool()(sync_lpr_rates)
mcp.tool()(get_lpr_sync_status)

# 图片旋转
mcp.tool()(extract_pdf_pages)
mcp.tool()(detect_orientation)
mcp.tool()(suggest_rename)
mcp.tool()(detect_single_page_orientation)
mcp.tool()(export_rotated_pdf)
mcp.tool()(export_rotated_images)

# 收件箱 - 消息
mcp.tool()(list_inbox_messages)
mcp.tool()(get_inbox_message)
mcp.tool()(rename_inbox_attachment)
mcp.tool()(download_inbox_attachment)
mcp.tool()(preview_inbox_attachment)

# 收件箱 - 来源
mcp.tool()(list_message_sources)
mcp.tool()(get_message_source)
mcp.tool()(create_message_source)
mcp.tool()(update_message_source)
mcp.tool()(delete_message_source)
mcp.tool()(sync_message_source)
mcp.tool()(sync_all_message_sources)

# 核心 - LLM 服务
mcp.tool()(chat_with_context)
mcp.tool()(get_conversation_history)
mcp.tool()(sync_prompt_templates)
mcp.tool()(list_available_models)
mcp.tool()(test_model_connection)

# 核心 - 系统配置
mcp.tool()(list_system_configs)
mcp.tool()(update_system_configs)
mcp.tool()(create_system_config)
mcp.tool()(patch_system_config)
mcp.tool()(delete_system_config)

# 核心 - 仪表盘
mcp.tool()(get_dashboard_stats)

# 核心 - 全局搜索
mcp.tool()(global_search)

# 核心 - 任务队列
mcp.tool()(list_queued_tasks)
mcp.tool()(list_completed_tasks)
mcp.tool()(list_failed_tasks)
mcp.tool()(list_scheduled_tasks)
mcp.tool()(delete_task)
mcp.tool()(delete_schedule)
mcp.tool()(resubmit_task)

# 核心 - POI 文档生成
mcp.tool()(poi_health)
mcp.tool()(generate_poi_complaint)
mcp.tool()(generate_report)

# 网络搜索
mcp.tool()(web_search)

# 工作流引擎
mcp.tool()(start_workflow)
mcp.tool()(list_workflows)
mcp.tool()(get_workflow_detail)
mcp.tool()(approve_workflow_step)
mcp.tool()(cancel_workflow)
