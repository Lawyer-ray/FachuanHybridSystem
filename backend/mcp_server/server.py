"""MCP Server 主入口 - 法穿SI Copilot"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from apps.agent.services.approval import RiskLevel, classify_risk
from mcp_server.client import FachuanApiError
from mcp_server.tools import (
    add_case_party,
    add_contract_party,
    analyze_template,
    approve_workflow_step,
    ask_user,
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
    confirm_memories,
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
    dispatch_research,
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
    forget_memory,
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
    list_pending_memories,
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
    recall_memory,
    remember,
    remove_contract_party,
    rename_inbox_attachment,
    rename_material_group,
    reorder_archive_materials,
    reorder_evidence_items,
    reorder_screenshots,
    reset_and_resync_case_materials,
    reset_extract_recording,
    reset_performance_metrics,
    restore_memory,
    resubmit_task,
    retry_sms_processing,
    rewrite_folder_file,
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
    verify_citations,
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

# 条件导入：东盟域外法查明（BARLC）
try:
    from mcp_server.tools import asean_law_countries, asean_law_read, asean_law_search, asean_law_verify

    _HAS_FOREIGN_LAW = True
except ImportError:
    _HAS_FOREIGN_LAW = False


mcp = MCPServer("法穿SI Copilot")

# ---------------------------------------------------------------------------
# 统一注册口:从审批分层权威表(apps.agent.services.approval)推导 MCP
# ToolAnnotations——与审批双表(Python/TS)共源,不另立第三份口径。
# 官方参考 server 均设 annotations;客户端(pi/其他 MCP host)可用
# readOnlyHint 做只读徽标/免审批策略,destructiveHint 标销毁型操作,
# idempotentHint 标幂等写(客户端重试安全)。payload 纪律:只有「读」
# 「销毁」「幂等写」带标注,create_/add_ 等非幂等写不带(默认即各项
# false,省 ~45B/工具 × 409 的 tools/list 体积)。
# ---------------------------------------------------------------------------
_DESTRUCTIVE_PREFIXES = ("delete_", "clear_", "reset_", "cleanup_")

#: 幂等前缀——同参数重复调用终态不变(客户端可安全重试)。
#: update_/save_/sync_/move_ 是绝对值覆盖/收敛/移动到目标语义;
#: delete_ 第二次 404 但环境无额外变化(spec 口径「no additional effect」)。
#: 刻意不含 create_/add_/toggle_/confirm_(重复=新副本/翻转/重复导入)。
_IDEMPOTENT_PREFIXES = ("update_", "save_", "sync_", "move_", "delete_")

#: 开放世界工具——真正发起外部网络/外部库交互(web_search/fetch_url 开放
#: 互联网;威科先行检索三件套)。本地任务状态读取(get/list/download
#: research task)不标——它们只读本地库。LLM 网关/受控解析后端(mineru/
#: textin)是基础设施而非开放世界实体,刻意不标。
_OPEN_WORLD_TOOLS = frozenset(
    {"web_search", "fetch_url", "capability_search", "check_law_references", "create_research_task"}
)


def _tool_annotations(name: str) -> ToolAnnotations:
    """按工具名推导 MCP 行为提示。销毁前缀或 HIGH/CRITICAL(递交/外发/
    归档确认等不可逆外部动作)标 destructive;LOW(读/无副作用计算)标
    readOnly;幂等前缀的写工具补 idempotentHint(重试安全,客户端可用于
    网络失败后的自动重试决策);开放世界工具补 openWorldHint(可与
    readOnly 并存——搜网不修改本地环境)。全部 hint 可组合。

    非销毁写(幂等/普通)必须**显式** ``destructive_hint=False``:
    MCP 规范(2025-11-25)对未声明 hint 的缺省是「assume worst」——
    destructiveHint 缺省按 true 理解,规范客户端会把 create_contract
    这类普通写当销毁型动作加确认拦截。官方 reference server 也是全量
    显式(含 false 值)。pi 侧逐键解析缺失即 false 不受影响,显式化
    的代价仅 ~3KB(对照剥 schema title 省下的 36KB),换取规范语义
    正确。openWorld 的缺省 true 刻意不逐工具补 false——409 个 ×24B
    ≈10KB 只防「客户端误以为会外发数据」这一低危误读,pi 不受影响,
    体量纪律优先。"""
    level = classify_risk(name)
    idempotent = name.startswith(_IDEMPOTENT_PREFIXES)
    open_world = name in _OPEN_WORLD_TOOLS
    destructive = name.startswith(_DESTRUCTIVE_PREFIXES) or level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    read_only = not destructive and level == RiskLevel.LOW
    return ToolAnnotations(
        idempotent_hint=True if idempotent else None,
        open_world_hint=True if open_world else None,
        destructive_hint=True if destructive else (False if not read_only else None),
        read_only_hint=True if read_only else None,
    )


#: 工具单次调用超过该毫秒数升 WARNING——pi 侧总超时 200s,30s 以上的调用
#: 律师侧已经能明确感到「卡住了」,值得在日志里一眼可见(而非 grep INFO)。
_SLOW_TOOL_MS = 30_000

logger = logging.getLogger(__name__)


def _log_tool_duration(name: str, started: float) -> None:
    """每次工具调用记一行耗时(成功失败都记,2026-10-25 审计五十一轮)。

    此前单工具耗时无处可查:AgentRun 只有 run 级聚合、消息表只有调用
    时刻、共享 MCP 日志只有 HTTP 级 ``POST /mcp``——「AI 很慢」排障只能
    靠猜。配套 ``mcp_server`` logger 单独配 INFO(logging.py),否则 root
    的 WARNING 级会把 INFO 全吞。超 ``_SLOW_TOOL_MS`` 升 WARNING。
    """
    elapsed_ms = (time.monotonic() - started) * 1000
    if elapsed_ms >= _SLOW_TOOL_MS:
        logger.warning("SLOW tool %s %.0fms", name, elapsed_ms)
    else:
        logger.info("tool %s %.0fms", name, elapsed_ms)


#: 宿主 pi 对工具输出按 20480 字节拦腰截断(2026-10-25 实测定案)。返回体
#: 序列化后接近/超过该线的工具,模型实际收到的是截断数据——此处只告警
#: 不截断(dict 截断会破坏 JSON 语义),让静默截断在共享 MCP 日志里可见,
#: 后续按日志逐工具收敛(下载类已由 client.download 闸门在源头拦)。
_TRUNCATION_WARN_BYTES = 19_000


def _warn_tool_result_size(name: str, result: Any) -> None:
    """返回体超截断线时记 WARNING(2026-10-25 审计六十二轮)。"""
    try:
        size = len(json.dumps(result, ensure_ascii=False, default=str))
    except (TypeError, ValueError):  # pragma: no cover - 不可序列化对象的兜底
        size = len(str(result))
    if size >= _TRUNCATION_WARN_BYTES:
        logger.warning("tool %s 返回 %d 字节,超出 pi 截断线 20480——模型只会收到截断数据", name, size)


def _t(func: Any) -> Any:
    """409 个工具的统一注册装饰器(替代裸 ``mcp.tool()``)。

    统一翻译 ``ValueError`` → ``FachuanApiError``(ToolError 子类):SDK 对
    非 ToolError 异常只回 ``Error executing tool X`` 不带消息——工具自己的
    参数校验文案(如「case_id/contract_id 至多传一个」「未知的 kind」)必须
    走 ToolError 才能直达模型供其自纠(2026-10-25 审计:list_folder_files
    空参调用的引导文案被吞成裸错误名)。

    另记每次调用耗时(见 ``_log_tool_duration``)、返回体超截断线告警
    (见 ``_warn_tool_result_size``),成功失败都记。
    """
    name = getattr(func, "__name__", "")

    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def _aw(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic()
            try:
                result = await func(*args, **kwargs)
            except ValueError as exc:
                raise FachuanApiError(str(exc)) from exc
            finally:
                _log_tool_duration(name, started)
            _warn_tool_result_size(name, result)
            return result

        target: Any = _aw
    else:

        @functools.wraps(func)
        def _sw(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic()
            try:
                result = func(*args, **kwargs)
            except ValueError as exc:
                raise FachuanApiError(str(exc)) from exc
            finally:
                _log_tool_duration(name, started)
            _warn_tool_result_size(name, result)
            return result

        target = _sw

    return mcp.tool(annotations=_tool_annotations(name))(target)


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
_t(verify_citations)

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

# 东盟域外法查明（插件缺失时不注册，与网上立案/保全同一处理口径）
if _HAS_FOREIGN_LAW:
    _t(asean_law_countries)
    _t(asean_law_search)
    _t(asean_law_read)
    _t(asean_law_verify)


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
    from django.db import close_old_connections
    from mcp.server.mcpserver.exceptions import ToolError

    from apps.core.exceptions.common import BusinessException

    drop = {"user", "org_access", "perm_open_access"}

    def _recycle_db_connections() -> None:
        """直接 ORM 工具的连接生命周期对齐 Django 请求周期。

        共享 MCP 进程里 workflow 工具直连 ORM,但没有 HTTP 请求周期——
        ``close_old_connections``(由 request_finished 信号驱动)永远不被
        调用,worker 线程的连接即使超过 CONN_MAX_AGE 也一直持有;
        CONN_HEALTH_CHECKS 探活同样只在该路径里生效。后果:PG 重启/主备
        切换后,全部 workflow 工具持续 OperationalError 直到 MCP 重启
        (同病已治:temporal worker 用每 5 分钟 close_old_connections)。
        进出各回收一次,代价是过期才关、新鲜即 no-op。"""

        close_old_connections()

    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            _recycle_db_connections()
            try:
                return await fn(*args, **kwargs)
            except BusinessException as exc:
                raise ToolError(str(exc) or exc.__class__.__name__) from exc
            except ObjectDoesNotExist as exc:
                # Django 原生「查无此物」同样是预期内失败(模型传错 id/slug),
                # 不翻译则黑盒——E2E 实测 start_workflow 坏 slug 只有半句报错
                raise ToolError(f"对象不存在: {exc}") from exc
            finally:
                _recycle_db_connections()

    else:

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            _recycle_db_connections()
            try:
                return fn(*args, **kwargs)
            except BusinessException as exc:
                raise ToolError(str(exc) or exc.__class__.__name__) from exc
            except ObjectDoesNotExist as exc:
                raise ToolError(f"对象不存在: {exc}") from exc
            finally:
                _recycle_db_connections()

    sig = inspect.signature(fn)
    # 注解字符串(本文件带 from __future__ import annotations)必须在**原函数**
    # 的模块名字空间里解析——wrapper 的 __globals__ 是 server.py,原生类型
    # (dict/Any)碰巧可见,业务侧私有别名(如 _RunStatusL)会变悬空 ForwardRef,
    # pydantic 建 Arguments 模型时炸「not fully defined」。这里先回填成真实类型。
    try:
        import typing as _typing

        hints = _typing.get_type_hints(fn, include_extras=True)
    except Exception:  # 解析失败回退原样(旧行为)
        hints = {}
    kept = []
    for p in sig.parameters.values():
        if p.name in drop:
            continue
        annotation = hints.get(p.name, p.annotation) if isinstance(p.annotation, str) else p.annotation
        kept.append(p.replace(annotation=annotation))
    wrapper.__signature__ = sig.replace(parameters=kept)  # type: ignore[attr-defined]
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
_t(ask_user)
_t(dispatch_research)

# 记忆：个人 / 团队 / 律所三级跨会话记忆（注入快照由 pi 扩展拉取，
# 模型只负责「写」「查」「删」三类主动动作）
_t(remember)
_t(recall_memory)
_t(forget_memory)
_t(restore_memory)
_t(list_pending_memories)
_t(confirm_memories)

# 对话附件：服务端读文件提取正文（base64 不进模型上下文）
_t(read_agent_attachment)
# 绑定文件夹引用：拖拽引用型，读原文件（不复制，路径即归属）
_t(list_folder_files)
_t(read_folder_file)
_t(rewrite_folder_file)

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


# ---------------------------------------------------------------------------
# 注册后统一瘦身:剥离 inputSchema 里的冗余自动 title
# ---------------------------------------------------------------------------
# pydantic 给每个参数生成与参数名同义的 title("case_type"→"Case Type"),
# 919 个参数 ≈ 20KB,占 tools/list 253KB 的 8%——零信息量,纯上下文税
# (direct 模式下常驻会话)。description(Annotated+Field)保留,title 全剥。
# 在所有 _t 注册完成后跑一遍;Tool.parameters 在 add_tool 时一次性生成,
# 原地改 dict 即持久。新增工具无需关心——这里统一处理。
def _strip_schema_titles(node: dict[str, Any] | list[Any]) -> int:
    """递归剥离 schema 节点里的 title 键,返回剥掉的数量(0=已是净的)。"""
    stripped = 0
    if isinstance(node, dict):
        if "title" in node:
            del node["title"]
            stripped += 1
        for value in node.values():
            stripped += _strip_schema_titles(value)
    elif isinstance(node, list):
        for item in node:
            stripped += _strip_schema_titles(item)
    return stripped


def _slim_registered_tool_schemas() -> int:
    total = 0
    for tool in mcp._tool_manager.list_tools():  # SDK 内部注册表,门禁测试钉死其行为
        total += _strip_schema_titles(tool.parameters)
    return total


#: 剥离计数；赋值本身即副作用（执行瘦身），且门禁测试读它，CodeQL 误报「未使用」，不可删除。
_SLIMMED_TITLES = _slim_registered_tool_schemas()
