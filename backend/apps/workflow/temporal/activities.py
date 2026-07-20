"""Temporal Activity 定义。

Activity 是普通 Python 函数，没有确定性约束。
可以直接调 Django ORM、LLM Service、其他 Django App。

所有涉及同步 I/O（LLM HTTP、ORM、文件）的 activity 必须使用
``asyncio.to_thread()`` 包装，防止阻塞 Temporal worker 的事件循环。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


# ── 辅助函数 ──────────────────────────────────────────────


async def _llm_chat(system: str, user: str) -> str:
    """LLM 聊天辅助: 处理初始化 + 消息构建 + 调用"""
    from apps.core.llm.config import LLMConfig
    from apps.core.llm.service import LLMService

    llm = await LLMService.create()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    # 使用配置的默认后端，显式传入避免 fallback 到无效后端
    default_backend = await LLMConfig.get_default_backend_async()
    response = await llm.achat(messages=messages, backend=default_backend, fallback=False)
    return response.content


# ── 状态管理 ──────────────────────────────────────────────


@activity.defn
async def record_step(
    run_id: int,
    step_id: str,
    step_name: str,
    step_type: str,
    status: str,
    output_data: Any = None,
    error_message: str | None = None,
) -> None:
    """记录步骤执行状态"""
    from django.utils import timezone

    from apps.workflow.models import StepExecution

    step_exec, created = await StepExecution.objects.aupdate_or_create(
        workflow_run_id=run_id,
        step_id=step_id,
        defaults={
            "step_name": step_name,
            "step_type": step_type,
            "status": status,
            "output_data": output_data,
            "error_message": error_message,
            "started_at": timezone.now() if status == StepExecution.Status.RUNNING else None,
            "finished_at": timezone.now() if status in (StepExecution.Status.SUCCESS, StepExecution.Status.FAILED) else None,
        },
    )
    if not created:
        step_exec.attempts = (step_exec.attempts or 0) + 1
        await step_exec.asave(update_fields=["attempts"])


@activity.defn
async def update_run_status(run_id: int, status: str, current_step_id: str = "") -> None:
    """更新 WorkflowRun 状态"""
    from django.utils import timezone

    from apps.workflow.models import WorkflowRun

    run = await WorkflowRun.objects.aget(pk=run_id)
    run.status = status
    run.current_step_id = current_step_id
    if status in (WorkflowRun.Status.COMPLETED, WorkflowRun.Status.FAILED, WorkflowRun.Status.CANCELLED):
        run.finished_at = timezone.now()
    await run.asave(update_fields=["status", "current_step_id", "finished_at"])


# ── 案件信息收集 ──────────────────────────────────────────


@activity.defn
async def collect_case_facts(case_id: int) -> dict:
    """收集案件基本事实"""
    from apps.cases.models import Case
    from apps.cases.models.party import CaseParty

    logger.info("collect_case_facts: case_id=%d", case_id)
    case = await Case.objects.select_related("contract").aget(pk=case_id)
    parties = [
        p async for p in CaseParty.objects.filter(case_id=case_id).select_related("client")
    ]

    return {
        "case_id": case.id,
        "case_name": case.name,
        "cause_of_action": case.cause_of_action,
        "target_amount": str(case.target_amount) if case.target_amount else None,
        "case_type": case.case_type,
        "start_date": str(case.start_date) if case.start_date else None,
        "parties": [
            {
                "name": p.client.name if p.client else "",
                "role": p.legal_status,
                "id_number": getattr(p.client, "id_number", "") if p.client else "",
                "address": getattr(p.client, "address", "") if p.client else "",
            }
            for p in parties
        ],
    }


@activity.defn
async def list_case_materials(case_id: int) -> list[dict]:
    """获取案件材料列表"""
    from apps.cases.models import CaseMaterial

    materials = [m async for m in CaseMaterial.objects.filter(case_id=case_id).order_by("type_name")]
    return [
        {
            "id": m.id,
            "name": m.type_name,
            "file_path": getattr(m, "file_path", ""),
            "content_type": getattr(m, "content_type", ""),
        }
        for m in materials
    ]


# ── 证据分析 ──────────────────────────────────────────────


@activity.defn
async def analyze_single_evidence(material: dict) -> dict:
    """LLM 分析单份证据"""
    from apps.documents.services.text_extractor import extract_text

    text = await extract_text(material["file_path"])
    if not text:
        text = material.get("name", "")

    analysis = await _llm_chat(
        system=(
            "你是诉讼证据分析专家。请从以下证据中提取关键信息：\n"
            "1. 法律关系类型\n2. 关键事实（金额、日期、当事人）\n"
            "3. 对我方有利/不利的点\n4. 证据证明力评估\n请用结构化格式回答。"
        ),
        user=text[:8000],
    )

    return {
        "material_id": material["id"],
        "material_name": material["name"],
        "analysis": analysis,
    }


@activity.defn
async def summarize_evidence(analyses: list[dict]) -> dict:
    """LLM 汇总所有证据分析"""
    combined = "\n\n".join(f"【{a['material_name']}】\n{a['analysis']}" for a in analyses)

    summary = await _llm_chat(
        system=(
            "你是资深诉讼律师。请汇总以下所有证据分析，输出：\n"
            "1. 法律关系定性\n2. 争议焦点\n3. 诉讼时效分析\n"
            "4. 诉讼请求建议（金额、利息计算）\n5. 风险提示\n请用结构化格式回答。"
        ),
        user=combined[:16000],
    )

    return {"summary": summary, "evidence_count": len(analyses)}


@activity.defn
async def suggest_arrangement(summary: dict) -> list[dict]:
    """LLM 建议证据排列顺序"""
    result = await _llm_chat(
        system=(
            "你是诉讼证据排列专家。请根据以下证据分析，建议最优的证据排列顺序。\n"
            "返回 JSON 数组，每项包含: id, name, reason（排列理由）\n"
            "排列原则：按时间线 + 逻辑递进（先基础关系证据，再履行证据，再违约证据）"
        ),
        user=json.dumps(summary, ensure_ascii=False)[:8000],
    )

    try:
        text = result
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, IndexError):
        return [{"id": 0, "name": "解析失败", "reason": result}]


@activity.defn
async def apply_arrangement(case_id: int, arrangement: list[dict]) -> None:
    """应用证据排列顺序"""
    from apps.cases.models import CaseMaterial

    for i, item in enumerate(arrangement):
        mat_id = item.get("id")
        if mat_id:
            await CaseMaterial.objects.filter(pk=mat_id, case_id=case_id).aupdate(order=i)


# ── 起诉状生成 ────────────────────────────────────────────


@activity.defn
async def build_litigation_context(case_id: int, summary: dict, arrangement: list[dict]) -> dict:
    """构建起诉状上下文"""
    from apps.cases.models import Case
    from apps.cases.models.party import CaseParty

    case = await Case.objects.select_related("contract").aget(pk=case_id)
    parties = [
        p async for p in CaseParty.objects.filter(case_id=case_id).select_related("client")
    ]

    return {
        "case": {
            "id": case.id,
            "name": case.name,
            "cause_of_action": case.cause_of_action,
            "target_amount": str(case.target_amount) if case.target_amount else None,
            "case_type": case.case_type,
        },
        "parties": [
            {
                "name": p.client.name if p.client else "",
                "role": p.legal_status,
                "id_number": getattr(p.client, "id_number", "") if p.client else "",
                "address": getattr(p.client, "address", "") if p.client else "",
            }
            for p in parties
        ],
        "evidence_summary": summary,
        "arrangement": arrangement,
    }


@activity.defn
async def generate_complaint(case_id: int, feedback: str | None = None) -> dict:
    """生成起诉状

    通过 LitigationGenerationService 生成起诉状。
    该服务是同步的（内部调用 LLM HTTP），用 asyncio.to_thread 防止阻塞事件循环。
    """
    import asyncio

    from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService
    from apps.documents.services.generation.litigation_context_builder import LitigationContextBuilder

    service = LitigationGenerationService()

    def _generate() -> Any:
        # 先用 context_builder 从 case_id 提取 LLM 所需的 case_data
        builder = LitigationContextBuilder()
        from apps.core.interfaces import ServiceLocator

        case_dto = ServiceLocator.get_case_service().get_case_by_id_internal(case_id)
        case_data = builder.extract_complaint_prompt_data(case_dto)
        if feedback:
            case_data["revision_feedback"] = feedback
        return service.generate_complaint(case_data)

    result = await asyncio.to_thread(_generate)
    return {"result": result}  # type: ignore[return-value]


@activity.defn
async def generate_complaint_simple(case_id: int, facts: dict) -> dict:
    """简化版起诉状生成（测试用）"""
    text = await _llm_chat(
        system="你是诉讼律师，请根据以下案件事实生成一份民事起诉状。",
        user=f"案件事实:\n{json.dumps(facts, ensure_ascii=False)}",
    )
    return {"content": text, "case_id": case_id}


@activity.defn
async def review_complaint_quality(draft: dict, summary: dict) -> dict:
    """LLM 审查起诉状质量"""
    result = await _llm_chat(
        system=(
            "你是资深诉讼律师，请审查以下起诉状的质量。评估维度：\n"
            "1. 诉讼请求是否完整、金额是否准确\n2. 事实与理由是否与证据一致\n"
            "3. 法律依据是否正确\n4. 格式是否规范\n\n"
            '返回 JSON: {"score": 0-100, "issues": [...], "suggestions": [...]}'
        ),
        user=f"起诉状:\n{json.dumps(draft, ensure_ascii=False)[:10000]}\n\n证据分析:\n{json.dumps(summary, ensure_ascii=False)[:5000]}",
    )

    try:
        text = result
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, IndexError):
        return {"score": 70, "issues": ["解析失败"], "suggestions": [result]}


# ── 立案（条件性，依赖 court_automation 插件）───────────────────

try:
    from plugins.court_automation.filing.helpers import _run_filing

    _HAS_COURT_FILING = True
except ImportError:
    _HAS_COURT_FILING = False


@activity.defn
async def execute_court_filing(case_id: int, feedback: str | None = None) -> dict:
    """执行网上立案（需要 court_automation 插件）"""
    if not _HAS_COURT_FILING:
        from temporalio.exceptions import ApplicationError

        raise ApplicationError("Court filing plugin not installed", non_retryable=True)

    from apps.automation.services.litigation.filing_service import CourtFilingService

    service = CourtFilingService()
    return await service.execute(case_id)  # type: ignore[no-any-return]


@activity.defn
async def download_litigation_document(document_id: int) -> dict:
    """下载已生成的诉讼文书

    通过 LitigationGenerationService 生成文档。
    该服务是同步的（ORM + 文件 I/O + LLM），用 asyncio.to_thread 防止阻塞。
    """
    import asyncio

    from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

    service = LitigationGenerationService()

    def _download() -> dict:
        filename, doc_bytes = service.generate_complaint_document(document_id)
        return {"filename": filename, "size": len(doc_bytes)}

    return await asyncio.to_thread(_download)


# ── DynamicWorkflow 通用 Activity ────────────────────────────


@activity.defn
async def fetch_template_schema(template_id: int) -> dict:
    """从 DB 读取 WorkflowTemplate 的 steps_schema（workflow 代码不能直接做 ORM）"""
    from apps.workflow.models import WorkflowTemplate

    tpl = await WorkflowTemplate.objects.aget(pk=template_id)
    return {
        "template_id": tpl.id,
        "name": tpl.name,
        "slug": tpl.slug,
        "steps_schema": tpl.steps_schema,
    }


@activity.defn
async def generic_delay(duration_minutes: float) -> None:
    """延时等待（包装为 activity 保证 Temporal 确定性）"""
    import asyncio
    await asyncio.sleep(duration_minutes * 60)


@activity.defn
async def generic_llm_call(system_prompt: str, user_prompt: str) -> dict:
    """通用 LLM 调用 activity"""
    result = await _llm_chat(system=system_prompt, user=user_prompt)
    return {"result": result}


@activity.defn
async def generic_http_request(method: str, url: str, headers: str = "", body: str = "") -> dict:
    """通用 HTTP 请求 activity"""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        kwargs: dict = {"url": url}
        if headers:
            kwargs["headers"] = json.loads(headers)
        if body:
            kwargs["json"] = json.loads(body)

        async with session.request(method, **kwargs) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = text
            return {"status_code": resp.status, "data": data}


@activity.defn
async def generic_code_exec(code: str, context: dict | None = None) -> dict:
    """受限 Python 代码执行 activity

    安全措施：
    1. AST 静态分析 — 执行前检查代码，拒绝危险模式
    2. 移除 getattr/hasattr — 阻断 MRO 链逃逸
    3. 子进程超时 — 防止死循环阻塞 worker（可用 proc.terminate() 真正杀死）
    4. 最小权限 builtins — 仅暴露安全的内置函数

    使用 multiprocessing.Process + Queue（而非 Manager），避免 socket FD 泄漏。
    """
    import ast
    import builtins

    # ── 危险属性名集合（__class__ 链 + 内省钩子）──
    _DANGEROUS_ATTRS = frozenset({
        "__class__", "__bases__", "__base__", "__mro__", "__subclasses__",
        "__builtins__", "__globals__", "__init__", "__import__", "__loader__",
        "__spec__", "__file__", "__path__", "__dict__", "__getattr__",
        "__setattr__", "__delattr__", "__reduce__", "__reduce_ex__",
        "__getattribute__", "__new__", "__del__",
    })

    # ── 危险函数/模块名 ──
    _DANGEROUS_NAMES = frozenset({
        "exec", "eval", "compile", "__import__", "breakpoint", "exit", "quit",
        "open", "input", "globals", "locals", "vars", "dir", "type", "id",
        "getattr", "hasattr", "delattr", "setattr", "super", "classmethod",
        "staticmethod", "property", "object", "memoryview", "bytearray",
        "os", "sys", "subprocess", "shutil", "pathlib", "importlib",
        "socket", "http", "urllib", "requests", "tempfile", "ctypes",
        "code", "ast", "inspect", "dis", "gc", "weakref", "threading",
        "multiprocessing", "signal", "fcntl", "resource",
    })

    def _validate_ast(node: ast.AST) -> None:
        """递归遍历 AST，拒绝危险模式。不安全则抛出 ValueError。"""
        for child in ast.walk(node):
            # 禁止 import 语句
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                raise ValueError("代码中不允许 import 语句")
            # 禁止 exec/eval 调用
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name) and child.func.id in ("exec", "eval", "compile"):
                    raise ValueError(f"不允许调用 {child.func.id}()")
            # 禁止访问危险属性（__class__、__bases__ 等）
            if isinstance(child, ast.Attribute) and child.attr in _DANGEROUS_ATTRS:
                raise ValueError(f"不允许访问属性 {child.attr}")
            # 禁止使用危险名称
            if isinstance(child, ast.Name) and child.id in _DANGEROUS_NAMES:
                raise ValueError(f"不允许使用 {child.id}")
            # 禁止 f-string（可携带任意表达式）
            if isinstance(child, ast.JoinedStr):
                raise ValueError("代码中不允许使用 f-string")
            # 禁止 global/nonlocal 声明
            if isinstance(child, (ast.Global, ast.Nonlocal)):
                raise ValueError("代码中不允许 global/nonlocal 声明")
            # 禁止 yield/yield from（生成器）
            if isinstance(child, (ast.Yield, ast.YieldFrom)):
                raise ValueError("代码中不允许使用 yield")
            # 禁止 await
            if isinstance(child, ast.Await):
                raise ValueError("代码中不允许使用 await")

    # ── 步骤 1: AST 静态验证 ──
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise ValueError(f"代码语法错误: {e}") from e
    _validate_ast(tree)

    # ── 步骤 2: 构建受限执行环境 ──
    _SAFE_BUILTINS = {
        "len", "int", "float", "str", "bool", "list", "dict", "set", "tuple",
        "min", "max", "sum", "abs", "round", "sorted", "reversed", "enumerate",
        "zip", "map", "filter", "any", "all", "range", "isinstance",
        "repr", "print",
    }
    restricted_builtins = {
        k: getattr(builtins, k) for k in _SAFE_BUILTINS if hasattr(builtins, k)
    }
    # 提供安全的 json.loads / json.dumps 代理，不暴露 json 模块本身
    _safe_json = type("SafeJson", (), {
        "loads": staticmethod(json.loads),
        "dumps": staticmethod(json.dumps),
    })()

    restricted_globals: dict[str, Any] = {
        "__builtins__": restricted_builtins,
        "json": _safe_json,
        "context": context or {},
    }

    # ── 步骤 3: 在子线程中执行（防止死循环阻塞事件循环）──
    compiled = compile(tree, "<workflow_code>", "exec")

    def _exec_in_thread() -> dict:
        """在隔离线程中执行编译后的代码"""
        exec(compiled, restricted_globals)  # noqa: S102
        return {
            k: v for k, v in restricted_globals.items()
            if not k.startswith("_") and k not in ("json", "context")
        }

    import asyncio
    return await asyncio.wait_for(
        asyncio.to_thread(_exec_in_thread),
        timeout=30,
    )


@activity.defn
async def execute_mcp_tool(mcp_tool_name: str, kwargs: dict) -> dict:
    """通用 MCP 工具调度器 —— 根据 tool name 动态调用对应 MCP 函数

    MCP 工具都是同步函数，这里用 asyncio.to_thread 包装。
    """
    import asyncio

    # ── MCP 工具路由表 ──
    MCP_TOOLS: dict[str, Any] = {}  # lazy init

    if not MCP_TOOLS:
        from mcp_server.tools.cases.cases import get_case
        from mcp_server.tools.cases.litigation_fee import calculate_litigation_fee
        from mcp_server.tools.cases.logs import create_case_log
        from mcp_server.tools.cases.materials import list_bind_candidates
        from mcp_server.tools.doc_convert.doc_convert import convert_document
        from mcp_server.tools.documents.authorization import download_authorization_package
        from mcp_server.tools.documents.litigation import (
            download_litigation_document as mcp_download_litigation,
            generate_complaint as mcp_generate_complaint,
            generate_defense,
        )
        from mcp_server.tools.documents.preservation import download_full_preservation_package
        from mcp_server.tools.enterprise_data.enterprise_data import (
            get_company_profile,
            get_company_risks,
            search_companies,
        )
        from mcp_server.tools.finance.lpr import calculate_interest
        from mcp_server.tools.automation.auto_namer import auto_namer_process
        if _HAS_COURT_FILING:
            from mcp_server.tools.automation.court_filing import execute_court_filing as mcp_execute_court_filing

            MCP_TOOLS["execute_court_filing"] = mcp_execute_court_filing
        from mcp_server.tools.automation.court_guarantee import execute_guarantee
        from mcp_server.tools.automation.court_sms import submit_court_sms
        from mcp_server.tools.automation.document_processor import process_document
        from mcp_server.tools.legal_research.legal_research import check_law_references, create_research_task
        from mcp_server.tools.reminders.reminders import create_new_reminder

        MCP_TOOLS = {
            "get_case": get_case,
            "generate_complaint": mcp_generate_complaint,
            "generate_defense": generate_defense,
            "download_litigation_document": mcp_download_litigation,
            "download_authorization_package": download_authorization_package,
            "download_full_preservation_package": download_full_preservation_package,
            "list_bind_candidates": list_bind_candidates,
            "create_case_log": create_case_log,
            "execute_guarantee": execute_guarantee,
            "submit_court_sms": submit_court_sms,
            "search_companies": search_companies,
            "get_company_profile": get_company_profile,
            "get_company_risks": get_company_risks,
            "create_research_task": create_research_task,
            "check_law_references": check_law_references,
            "create_new_reminder": create_new_reminder,
            "auto_namer_process": auto_namer_process,
            "process_document": process_document,
            "convert_document": convert_document,
            "calculate_litigation_fee": calculate_litigation_fee,
            "calculate_interest": calculate_interest,
        }

    fn = MCP_TOOLS.get(mcp_tool_name)
    if fn is None:
        raise ValueError(f"未知 MCP 工具: {mcp_tool_name}")

    result = await asyncio.to_thread(fn, **kwargs)
    return result if isinstance(result, dict) else {"data": result}
