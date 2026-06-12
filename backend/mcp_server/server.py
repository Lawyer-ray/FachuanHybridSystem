"""MCP Server 主入口 - 法穿AI Copilot"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_server.tools import (
    add_case_party,
    assign_lawyer,
    assign_sms_case,
    auto_namer_process,
    auto_namer_process_by_path,
    batch_create_cases,
    batch_create_clients,
    bind_guarantee_quote,
    bind_materials,
    browse_case_folders,
    browse_folders,
    calculate_interest,
    calculate_litigation_fee,
    cancel_extract_recording,
    cancel_pdf_split,
    capability_search,
    check_law_references,
    check_oa_credential,
    confirm_pdf_split,
    confirm_party,
    convert_document,
    create_case,
    create_case_folder_binding,
    create_case_log,
    create_case_number,
    create_client,
    create_contract,
    create_contract_with_cases,
    create_credential,
    create_delivery_schedule,
    create_document_template,
    create_export,
    create_folder_binding,
    create_full_case,
    create_grant,
    create_lawfirm,
    create_lawyer,
    create_new_reminder,
    create_payment,
    create_pdf_split_job,
    create_preservation_quote,
    create_project,
    create_property_clue,
    create_research_task,
    create_scan_stage,
    create_supplementary_agreement,
    create_team,
    create_template_binding,
    create_message_source,
    delete_all_materials,
    delete_case,
    delete_case_assignment,
    delete_case_folder_binding,
    delete_case_log,
    delete_case_number,
    delete_case_party,
    delete_contract,
    delete_credential,
    delete_court_sms,
    delete_folder_binding,
    delete_grant,
    delete_guarantee_binding,
    delete_guarantee_quote,
    delete_identity_doc,
    delete_lawfirm,
    delete_lawyer,
    delete_material,
    delete_payment,
    delete_property_clue,
    delete_recording,
    delete_reminder,
    delete_screenshot,
    delete_supplementary_agreement,
    delete_team,
    delete_template_binding,
    delete_message_source,
    detect_orientation,
    detect_single_page_orientation,
    download_all_research_results,
    download_contract_document,
    download_contract_folder,
    download_export,
    download_inbox_attachment,
    download_invoices,
    download_normalized_result,
    download_pdf_split_raw,
    download_pdf_split_result,
    download_research_result,
    download_review_original,
    download_review_result,
    download_sms_document,
    download_sms_documents,
    enterprise_prefill,
    enterprise_search,
    ensure_guarantee_quote,
    execute_case_import,
    execute_court_filing,
    execute_guarantee,
    execute_preservation_quote,
    export_rotated_images,
    export_rotated_pdf,
    extract_pdf_pages,
    extract_recording,
    generate_case_template,
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
    get_court_filing_case_info,
    get_court_filing_session,
    get_client,
    get_client_import_session,
    get_company_personnel,
    get_company_profile,
    get_company_risks,
    get_company_shareholders,
    get_contract,
    get_contract_all_parties,
    get_contract_folder_path,
    get_credential,
    get_court_sms_detail,
    get_delivery_schedule,
    get_document_template,
    get_export_statuses,
    get_export_task,
    get_export_types,
    get_filing_status,
    get_folder_binding,
    get_finance_stats,
    get_guarantee_case_info,
    get_guarantee_session,
    get_identity_doc,
    get_inbox_message,
    get_invoice_task_status,
    get_latest_lpr_rate,
    get_lawfirm,
    get_lawyer,
    get_lpr_sync_status,
    get_message_source,
    get_pdf_split_job,
    get_pdf_split_page_preview,
    get_person_profile,
    get_preservation_quote,
    get_property_clue,
    get_property_clue_content_template,
    get_recording,
    get_reminder,
    get_research_task,
    get_review_models,
    get_review_status,
    get_scan_status,
    get_supplementary_agreement,
    get_target_options,
    get_team,
    list_all_reminders,
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
    list_cloud_storage_accounts,
    list_contracts,
    list_court_sms,
    list_courts_data,
    list_credentials,
    list_delivery_schedules,
    list_doc_convert_types,
    list_document_templates,
    list_enterprise_providers,
    list_folder_templates,
    list_grants,
    list_inbox_messages,
    list_lawfirms,
    list_lawyers,
    list_lpr_rates,
    list_message_sources,
    list_oa_configs,
    list_payments,
    list_placeholders,
    list_preservation_quotes,
    list_projects,
    list_property_clues,
    list_recordings,
    list_reminder_types,
    list_research_results,
    list_scan_subfolders,
    list_screenshots,
    list_supplementary_agreements,
    list_teams,
    list_template_bindings,
    normalize_contract_format,
    parse_client_text,
    parse_reminders_from_text,
    preview_contract_context,
    preview_inbox_attachment,
    preview_placeholders,
    query_document_delivery,
    quick_recognize_invoice,
    rename_inbox_attachment,
    rename_material_group,
    reorder_screenshots,
    reset_extract_recording,
    retry_guarantee_quote,
    retry_preservation_quote,
    retry_sms_processing,
    save_group_order,
    search_bidding_info,
    search_cases,
    search_companies,
    start_folder_scan,
    submit_captcha_answer,
    submit_court_sms,
    suggest_rename,
    sync_all_message_sources,
    sync_lpr_rates,
    sync_message_source,
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
    update_contract,
    update_contract_lawyers,
    update_credential,
    update_delivery_schedule,
    update_grant,
    update_lawfirm,
    update_lawyer,
    update_message_source,
    update_payment,
    update_property_clue,
    update_recording,
    update_reminder,
    update_screenshot,
    update_supplementary_agreement,
    update_team,
    upload_contract_for_review,
    upload_invoices,
    validate_id_card,
    web_search,
)

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
mcp.tool()(enterprise_search)
mcp.tool()(enterprise_prefill)
mcp.tool()(get_identity_doc)
mcp.tool()(delete_identity_doc)
mcp.tool()(validate_id_card)
mcp.tool()(check_oa_credential)

# 客户财产线索
mcp.tool()(list_property_clues)
mcp.tool()(create_property_clue)
mcp.tool()(get_property_clue)
mcp.tool()(update_property_clue)
mcp.tool()(delete_property_clue)
mcp.tool()(get_property_clue_content_template)

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

# 自动化 - 财产保全询价
mcp.tool()(create_preservation_quote)
mcp.tool()(list_preservation_quotes)
mcp.tool()(get_preservation_quote)
mcp.tool()(execute_preservation_quote)
mcp.tool()(retry_preservation_quote)

# 自动化 - 文书送达
mcp.tool()(query_document_delivery)
mcp.tool()(list_delivery_schedules)
mcp.tool()(create_delivery_schedule)
mcp.tool()(get_delivery_schedule)
mcp.tool()(update_delivery_schedule)

# 自动化 - 验证码
mcp.tool()(get_captcha_image)
mcp.tool()(submit_captcha_answer)

# 自动化 - 自动命名
mcp.tool()(auto_namer_process)
mcp.tool()(auto_namer_process_by_path)

# 自动化 - 网上立案
mcp.tool()(get_court_filing_case_info)
mcp.tool()(get_court_filing_session)
mcp.tool()(execute_court_filing)

# 自动化 - 诉讼保全
mcp.tool()(get_guarantee_case_info)
mcp.tool()(get_guarantee_session)
mcp.tool()(execute_guarantee)
mcp.tool()(ensure_guarantee_quote)
mcp.tool()(bind_guarantee_quote)
mcp.tool()(delete_guarantee_quote)
mcp.tool()(retry_guarantee_quote)
mcp.tool()(delete_guarantee_binding)

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

# 文书生产
mcp.tool()(list_document_templates)
mcp.tool()(get_document_template)
mcp.tool()(create_document_template)
mcp.tool()(list_folder_templates)
mcp.tool()(list_placeholders)
mcp.tool()(preview_placeholders)
mcp.tool()(preview_contract_context)
mcp.tool()(download_contract_document)
mcp.tool()(download_contract_folder)

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

# 网络搜索
mcp.tool()(web_search)
