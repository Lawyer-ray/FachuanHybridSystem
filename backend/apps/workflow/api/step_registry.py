"""步骤注册表 — 暴露所有可用的 MCP 工具 / API / Activity 作为工作流步骤

前端编排器用此数据渲染步骤面板和属性表单。
"""

from __future__ import annotations

from typing import Any

# ── 步骤分类 ──────────────────────────────────────────────────────────────────

STEP_CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "flow",
        "name": "流程控制",
        "icon": "GitBranch",
        "steps": [
            {
                "id": "gate",
                "name": "人工审批门",
                "type": "gate",
                "description": "暂停流程，等待人工审批后继续",
                "icon": "ShieldCheck",
                "config_schema": {
                    "signal_key": {"type": "string", "required": True, "label": "Signal Key", "placeholder": "e.g. confirm_facts_approved"},
                    "prompt": {"type": "textarea", "required": False, "label": "审批提示", "placeholder": "展示给审批人的说明文字"},
                    "timeout_hours": {"type": "number", "required": False, "label": "超时(小时)", "default": 72},
                },
            },
            {
                "id": "wait_event",
                "name": "等待外部事件",
                "type": "wait",
                "description": "等待外部事件触发后继续（如法院短信、邮件回复）",
                "icon": "Clock",
                "config_schema": {
                    "event_type": {"type": "select", "required": True, "label": "事件类型", "options": ["court_sms", "email_reply", "custom"]},
                    "timeout_hours": {"type": "number", "required": False, "label": "超时(小时)", "default": 168},
                },
            },
            {
                "id": "condition",
                "name": "条件分支",
                "type": "condition",
                "description": "根据条件判断走不同分支",
                "icon": "GitFork",
                "config_schema": {
                    "field": {"type": "string", "required": True, "label": "判断字段", "placeholder": "e.g. previous_step.result.need_complaint"},
                    "operator": {"type": "select", "required": True, "label": "运算符", "options": ["eq", "neq", "gt", "lt", "contains", "exists"]},
                    "value": {"type": "string", "required": True, "label": "比较值"},
                },
            },
            {
                "id": "delay",
                "name": "延时等待",
                "type": "delay",
                "description": "暂停指定时间后继续",
                "icon": "Timer",
                "config_schema": {
                    "duration_minutes": {"type": "number", "required": True, "label": "等待时间(分钟)", "default": 5},
                },
            },
            {
                "id": "llm_call",
                "name": "LLM 调用",
                "type": "llm",
                "description": "调用大语言模型处理文本",
                "icon": "Brain",
                "config_schema": {
                    "system_prompt": {"type": "textarea", "required": True, "label": "系统提示词"},
                    "user_prompt_template": {"type": "textarea", "required": True, "label": "用户提示词模板", "help": "可用 {{previous_step.output}} 引用前序步骤输出"},
                    "model": {"type": "string", "required": False, "label": "模型", "placeholder": "留空使用默认模型"},
                    "output_key": {"type": "string", "required": False, "label": "输出字段名", "default": "result"},
                },
            },
            {
                "id": "http_request",
                "name": "HTTP 请求",
                "type": "http",
                "description": "发送 HTTP 请求调用外部 API",
                "icon": "Globe",
                "config_schema": {
                    "method": {"type": "select", "required": True, "label": "方法", "options": ["GET", "POST", "PUT", "DELETE", "PATCH"]},
                    "url": {"type": "string", "required": True, "label": "URL", "placeholder": "https://api.example.com/endpoint"},
                    "headers": {"type": "textarea", "required": False, "label": "请求头 (JSON)"},
                    "body": {"type": "textarea", "required": False, "label": "请求体 (JSON)"},
                },
            },
            {
                "id": "code_exec",
                "name": "代码执行",
                "type": "code",
                "description": "执行自定义 Python 代码片段",
                "icon": "Code",
                "config_schema": {
                    "code": {"type": "textarea", "required": True, "label": "Python 代码", "help": "可用 context['previous_output'] 访问前序步骤输出"},
                    "timeout_seconds": {"type": "number", "required": False, "label": "超时(秒)", "default": 30},
                },
            },
        ],
    },
    {
        "id": "cases",
        "name": "案件管理",
        "icon": "Briefcase",
        "steps": [
            {
                "id": "collect_case_facts",
                "name": "收集案件事实",
                "type": "activity",
                "description": "从数据库收集案件基本事实信息",
                "icon": "FileSearch",
                "mcp_tool": "get_case",
                "config_schema": {
                    "case_id_source": {"type": "select", "required": True, "label": "案件ID来源", "options": ["workflow_input", "previous_step"], "default": "workflow_input"},
                },
            },
            {
                "id": "list_case_materials",
                "name": "获取案件材料",
                "type": "activity",
                "description": "获取案件关联的全部材料列表",
                "icon": "Files",
                "mcp_tool": "list_bind_candidates",
                "config_schema": {},
            },
            {
                "id": "create_case_log",
                "name": "创建案件日志",
                "type": "activity",
                "description": "在案件中添加一条操作日志",
                "icon": "BookOpen",
                "mcp_tool": "create_case_log",
                "config_schema": {
                    "content_template": {"type": "textarea", "required": True, "label": "日志内容模板", "help": "可用 {{变量}} 插入前序步骤输出"},
                },
            },
        ],
    },
    {
        "id": "evidence",
        "name": "证据分析",
        "icon": "Search",
        "steps": [
            {
                "id": "analyze_single_evidence",
                "name": "分析单份证据",
                "type": "activity",
                "description": "用 LLM 分析单份证据材料",
                "icon": "Microscope",
                "config_schema": {},
            },
            {
                "id": "summarize_evidence",
                "name": "汇总证据分析",
                "type": "activity",
                "description": "LLM 汇总所有证据分析结果",
                "icon": "BarChart3",
                "config_schema": {},
            },
            {
                "id": "suggest_arrangement",
                "name": "建议证据排列",
                "type": "activity",
                "description": "LLM 建议证据排列顺序",
                "icon": "ArrowUpDown",
                "config_schema": {},
            },
            {
                "id": "apply_arrangement",
                "name": "应用排列顺序",
                "type": "activity",
                "description": "将建议的排列顺序应用到案件",
                "icon": "CheckCircle",
                "config_schema": {},
            },
        ],
    },
    {
        "id": "documents",
        "name": "文书生成",
        "icon": "FileText",
        "steps": [
            {
                "id": "generate_complaint",
                "name": "生成起诉状",
                "type": "activity",
                "description": "基于案件事实和证据生成起诉状",
                "icon": "ScrollText",
                "mcp_tool": "generate_complaint",
                "config_schema": {
                    "template_id": {"type": "number", "required": False, "label": "模板ID"},
                    "feedback": {"type": "textarea", "required": False, "label": "修改意见"},
                },
            },
            {
                "id": "generate_defense",
                "name": "生成答辩状",
                "type": "activity",
                "description": "基于案件事实生成答辩状",
                "icon": "Shield",
                "mcp_tool": "generate_defense",
                "config_schema": {},
            },
            {
                "id": "review_complaint_quality",
                "name": "审查文书质量",
                "type": "activity",
                "description": "LLM 审查生成的文书质量",
                "icon": "CheckSquare",
                "config_schema": {},
            },
            {
                "id": "download_litigation_document",
                "name": "下载诉讼文书",
                "type": "activity",
                "description": "下载已生成的诉讼文书文件",
                "icon": "Download",
                "mcp_tool": "download_litigation_document",
                "config_schema": {
                    "document_id_source": {"type": "select", "required": True, "label": "文档ID来源", "options": ["previous_step", "manual"], "default": "previous_step"},
                    "document_id": {"type": "number", "required": False, "label": "文档ID"},
                },
            },
            {
                "id": "download_authorization_package",
                "name": "下载授权材料包",
                "type": "activity",
                "description": "打包下载授权委托书等材料",
                "icon": "Package",
                "mcp_tool": "download_authorization_package",
                "config_schema": {},
            },
            {
                "id": "download_preservation_docs",
                "name": "下载保全文书",
                "type": "activity",
                "description": "下载保全申请书等材料",
                "icon": "Lock",
                "mcp_tool": "download_full_preservation_package",
                "config_schema": {},
            },
        ],
    },
    {
        "id": "litigation",
        "name": "诉讼流程",
        "icon": "Scale",
        "steps": [
            {
                "id": "build_litigation_context",
                "name": "构建诉讼上下文",
                "type": "activity",
                "description": "整合案件数据 + 证据分析构建起诉上下文",
                "icon": "Database",
                "config_schema": {},
            },
            {
                "id": "execute_guarantee",
                "name": "执行诉讼保全",
                "type": "activity",
                "description": "执行诉讼保全操作",
                "icon": "Umbrella",
                "mcp_tool": "execute_guarantee",
                "config_schema": {},
            },
            {
                "id": "submit_court_sms",
                "name": "提交法院短信",
                "type": "activity",
                "description": "向法院提交短信通知",
                "icon": "MessageSquare",
                "mcp_tool": "submit_court_sms",
                "config_schema": {},
            },
        ],
    },
    {
        "id": "enterprise",
        "name": "企业数据",
        "icon": "Building2",
        "steps": [
            {
                "id": "search_companies",
                "name": "搜索企业",
                "type": "activity",
                "description": "通过天眼查/企查查搜索企业信息",
                "icon": "Search",
                "mcp_tool": "search_companies",
                "config_schema": {
                    "query_template": {"type": "string", "required": True, "label": "搜索关键词模板"},
                },
            },
            {
                "id": "get_company_profile",
                "name": "获取企业信息",
                "type": "activity",
                "description": "获取企业详细工商信息",
                "icon": "IdCard",
                "mcp_tool": "get_company_profile",
                "config_schema": {
                    "company_name_source": {"type": "select", "required": True, "label": "企业名来源", "options": ["workflow_input", "previous_step"], "default": "workflow_input"},
                },
            },
            {
                "id": "get_company_risks",
                "name": "获取企业风险",
                "type": "activity",
                "description": "获取企业风险信息（诉讼、失信等）",
                "icon": "AlertTriangle",
                "mcp_tool": "get_company_risks",
                "config_schema": {},
            },
        ],
    },
    {
        "id": "legal_research",
        "name": "法律检索",
        "icon": "BookMarked",
        "steps": [
            {
                "id": "create_research_task",
                "name": "创建检索任务",
                "type": "activity",
                "description": "创建法律文献检索任务",
                "icon": "SearchCode",
                "mcp_tool": "create_research_task",
                "config_schema": {
                    "query_template": {"type": "textarea", "required": True, "label": "检索关键词模板"},
                },
            },
            {
                "id": "check_law_references",
                "name": "核查法条引用",
                "type": "activity",
                "description": "核查文书中引用的法律条文是否准确",
                "icon": "BookCheck",
                "mcp_tool": "check_law_references",
                "config_schema": {},
            },
        ],
    },
    {
        "id": "notifications",
        "name": "通知与提醒",
        "icon": "Bell",
        "steps": [
            {
                "id": "create_reminder",
                "name": "创建提醒",
                "type": "activity",
                "description": "创建一条定时提醒",
                "icon": "AlarmClock",
                "mcp_tool": "create_new_reminder",
                "config_schema": {
                    "title_template": {"type": "string", "required": True, "label": "提醒标题模板"},
                    "due_days": {"type": "number", "required": False, "label": "几天后提醒", "default": 3},
                },
            },
            {
                "id": "send_message",
                "name": "发送消息",
                "type": "activity",
                "description": "通过消息中心发送通知",
                "icon": "Mail",
                "config_schema": {
                    "channel": {"type": "select", "required": True, "label": "渠道", "options": ["feishu", "dingtalk", "wechat_work", "email"]},
                    "content_template": {"type": "textarea", "required": True, "label": "消息内容模板"},
                },
            },
        ],
    },
    {
        "id": "automation",
        "name": "自动化工具",
        "icon": "Zap",
        "steps": [
            {
                "id": "auto_namer",
                "name": "智能文件命名",
                "type": "activity",
                "description": "AI 自动重命名文件",
                "icon": "Rename",
                "mcp_tool": "auto_namer_process",
                "config_schema": {},
            },
            {
                "id": "process_document",
                "name": "文档处理",
                "type": "activity",
                "description": "自动处理文档（OCR、分类等）",
                "icon": "FileScan",
                "mcp_tool": "process_document",
                "config_schema": {},
            },
            {
                "id": "convert_document",
                "name": "文档格式转换",
                "type": "activity",
                "description": "转换文档格式（PDF↔DOCX 等）",
                "icon": "RefreshCw",
                "mcp_tool": "convert_document",
                "config_schema": {
                    "target_format": {"type": "select", "required": True, "label": "目标格式", "options": ["pdf", "docx", "xlsx", "png"]},
                },
            },
            {
                "id": "calculate_litigation_fee",
                "name": "计算诉讼费",
                "type": "activity",
                "description": "自动计算诉讼费用",
                "icon": "Calculator",
                "mcp_tool": "calculate_litigation_fee",
                "config_schema": {},
            },
            {
                "id": "calculate_interest",
                "name": "计算利息",
                "type": "activity",
                "description": "根据 LPR 计算利息金额",
                "icon": "Percent",
                "mcp_tool": "calculate_interest",
                "config_schema": {},
            },
        ],
    },
]

# ── 条件性步骤：court_automation 插件可用时才注册 ────────────────
try:
    from plugins.court_automation.filing.helpers import _run_filing  # noqa: F401

    _HAS_COURT_FILING = True
except ImportError:
    _HAS_COURT_FILING = False

if _HAS_COURT_FILING:
    _COURT_FILING_STEP = {
        "id": "execute_court_filing",
        "name": "执行网上立案",
        "type": "activity",
        "description": "自动执行法院网上立案操作",
        "icon": "Send",
        "mcp_tool": "execute_court_filing",
        "config_schema": {
            "case_id_source": {
                "type": "select",
                "required": True,
                "label": "案件ID来源",
                "options": ["workflow_input", "previous_step"],
                "default": "workflow_input",
            },
        },
    }
    # 在诉讼流程分类中，build_litigation_context 之后插入
    for _cat in STEP_CATEGORIES:
        if _cat["id"] == "litigation":
            _ctx_idx = next(
                i for i, s in enumerate(_cat["steps"]) if s["id"] == "build_litigation_context"
            )
            _cat["steps"].insert(_ctx_idx + 1, _COURT_FILING_STEP)
            break


def get_step_registry() -> list[dict[str, Any]]:
    """返回完整步骤注册表"""
    return STEP_CATEGORIES


def get_flat_step_list() -> list[dict[str, Any]]:
    """返回扁平化的步骤列表（用于搜索）"""
    steps = []
    for cat in STEP_CATEGORIES:
        for step in cat["steps"]:
            steps.append({**step, "category_id": cat["id"], "category_name": cat["name"]})
    return steps


def find_step(step_id: str) -> dict[str, Any] | None:
    """根据 step_id 查找步骤定义"""
    for step in get_flat_step_list():
        if step["id"] == step_id:
            return step
    return None
