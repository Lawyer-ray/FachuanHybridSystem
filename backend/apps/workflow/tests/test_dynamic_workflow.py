"""DynamicWorkflow 端到端集成测试

用法 (前提: Temporal Server + Django + Worker 已启动):
  cd backend/apiSystem && PYTHONPATH=.. ../.venv/bin/python -m apps.workflow.tests.test_dynamic_workflow
"""

from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django  # noqa: E402

django.setup()

from temporalio.client import Client  # noqa: E402

TEMPORAL_ADDRESS = "localhost:7233"
TASK_QUEUE = "fachuan-workflow"


# 测试模板: 3 种步骤类型 → 验证 DynamicWorkflow 调度
TEST_STEPS = [
    {
        "id": "collect_facts",
        "name": "收集案件事实",
        "type": "activity",
        "mcp_tool": "get_case",
        "icon": "FileSearch",
        "config": {},
        "timeout": "30s",
        "retry_max": 3,
        "on_fail": "abort",
    },
    {
        "id": "confirm_facts",
        "name": "人工确认事实",
        "type": "gate",
        "icon": "ShieldCheck",
        "config": {
            "signal_key": "confirm_facts_approved",
            "prompt": "请确认案件事实是否正确",
            "timeout_hours": 1,
        },
        "timeout": "30s",
        "retry_max": 1,
        "on_fail": "abort",
    },
    {
        "id": "list_materials",
        "name": "获取案件材料",
        "type": "activity",
        "mcp_tool": "list_bind_candidates",
        "icon": "Files",
        "config": {},
        "timeout": "30s",
        "retry_max": 3,
        "on_fail": "abort",
    },
]


async def run_dynamic_workflow_test() -> bool:
    """测试 DynamicWorkflow 完整流程: 创建模板 → 启动 → gate 审批 → 完成"""
    print("=" * 60)
    print("端到端测试: DynamicWorkflow")
    print("=" * 60)

    # 1) 连接 Temporal
    try:
        client = await Client.connect(TEMPORAL_ADDRESS)
        print("✅ 连接 Temporal Server")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False

    # 2) 获取测试案件
    from apps.cases.models import Case

    first_case = await Case.objects.afirst()
    if not first_case:
        print("❌ 没有可用的案件，请先创建一个案件")
        return False
    case_id = first_case.id
    print(f"✅ 使用案件: id={case_id}, name={first_case.name}")

    # 3) 创建/更新 DynamicWorkflow 模板
    from apps.workflow.models import WorkflowRun, WorkflowTemplate

    template_slug = "dynamic-test-e2e"
    template, created = await WorkflowTemplate.objects.aget_or_create(
        slug=template_slug,
        defaults={
            "name": "DynamicWorkflow E2E 测试模板",
            "category": "litigation",
            "description": "用于 e2e 测试",
            "temporal_workflow_name": "DynamicWorkflow",
            "is_active": True,
            "steps_schema": TEST_STEPS,
        },
    )
    if not created:
        template.steps_schema = TEST_STEPS
        template.temporal_workflow_name = "DynamicWorkflow"
        await template.asave(update_fields=["steps_schema", "temporal_workflow_name"])
    print(f"✅ 模板准备: {template.name} (id={template.id}, slug={template.slug})")

    # 4) 启动 DynamicWorkflow
    workflow_id = f"dynamic-e2e-{int(asyncio.get_event_loop().time())}"
    run = await WorkflowRun.objects.acreate(
        template=template,
        case_id=case_id,
        temporal_workflow_id=workflow_id,
        temporal_run_id="",
        status=WorkflowRun.Status.RUNNING,
    )

    try:
        handle = await client.start_workflow(
            "DynamicWorkflow",
            args=[{
                "case_id": case_id,
                "run_id": run.id,
                "template_id": template.id,
            }],
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )
        run.temporal_run_id = handle.result_run_id
        await run.asave(update_fields=["temporal_run_id"])
        print(f"✅ DynamicWorkflow 启动: {workflow_id}")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 5) 等待 gate (confirm_facts)
    print("⏳ 等待 confirm_facts gate...")
    for i in range(60):
        await asyncio.sleep(1)
        await run.arefresh_from_db()
        if run.status == WorkflowRun.Status.WAITING_HUMAN:
            break
        if run.status == WorkflowRun.Status.FAILED:
            print(f"❌ Workflow 失败: status={run.status}")
            steps = [s async for s in run.step_executions.all()]
            for s in steps:
                print(f"  {s.step_id}: {s.status} - {s.error_message or ''}")
            return False
        if i % 10 == 9:
            print(f"  ... 当前状态: {run.status}, step={run.current_step_id}")

    if run.status != WorkflowRun.Status.WAITING_HUMAN:
        print(f"❌ 超时等待 gate: status={run.status}, step={run.current_step_id}")
        return False
    print(f"✅ 进入 gate: step={run.current_step_id}")

    # 6) 检查 step 记录
    steps_before = [s async for s in run.step_executions.all()]
    print(f"✅ Gate 前 StepExecution 记录: {len(steps_before)} 步")
    for s in steps_before:
        print(f"  {s.step_id:20s} | {s.step_type:10s} | {s.status}")

    # 验证 collect_facts 有输出
    collect_step = next((s for s in steps_before if s.step_id == "collect_facts"), None)
    if not collect_step or collect_step.status != "success":
        print(f"❌ collect_facts 步骤异常: {collect_step.status if collect_step else 'not found'}")
        return False
    if not collect_step.output_data:
        print("❌ collect_facts 无输出数据")
        return False
    print(f"✅ collect_facts 输出: {str(collect_step.output_data)[:80]}...")

    # 7) 发送 gate_approved 信号 (通过)
    signal_handle = client.get_workflow_handle(workflow_id)
    await signal_handle.signal(
        "gate_approved",
        {"step_id": "confirm_facts", "approved": True, "comment": "事实确认通过"},
    )
    print("✅ 发送 gate_approved 信号 (approved=True)")

    # 8) 等待完成
    print("⏳ 等待 workflow 完成...")
    for i in range(60):
        await asyncio.sleep(1)
        await run.arefresh_from_db()
        if run.status == WorkflowRun.Status.COMPLETED:
            break
        if run.status == WorkflowRun.Status.FAILED:
            print(f"❌ Workflow 失败")
            all_steps = [s async for s in run.step_executions.all()]
            for s in all_steps:
                print(f"  {s.step_id}: {s.status} - {s.error_message or ''}")
            return False
        if i % 15 == 14:
            print(f"  ... 当前状态: {run.status}, step={run.current_step_id}")

    if run.status != WorkflowRun.Status.COMPLETED:
        print(f"❌ 超时: status={run.status}")
        return False

    # 9) 验证最终结果
    await run.arefresh_from_db()
    all_steps = [s async for s in run.step_executions.order_by("step_id").all()]

    print()
    print("=" * 60)
    print(f"状态: {run.status}")
    print(f"步骤 ({len(all_steps)}):")
    for s in all_steps:
        output_preview = str(s.output_data)[:80] if s.output_data else ""
        print(f"  {s.step_id:25s} | {s.step_type:10s} | {s.status:10s} | {output_preview}")
    print("=" * 60)

    # 验证断言
    ok = True
    if run.status != WorkflowRun.Status.COMPLETED:
        print(f"❌ 状态不是 COMPLETED: {run.status}")
        ok = False
    if len(all_steps) < 3:
        print(f"❌ 步骤数不足: {len(all_steps)} < 3")
        ok = False

    step_ids = [s.step_id for s in all_steps]
    for expected in ("collect_facts", "confirm_facts", "list_materials"):
        if expected not in step_ids:
            print(f"❌ 缺少 {expected} 步骤记录")
            ok = False

    # 检查各步骤状态
    for s in all_steps:
        if s.status != "success":
            print(f"❌ 步骤 {s.step_id} 状态异常: {s.status}")
            ok = False

    # 检查 list_materials 有输出
    materials_step = next((s for s in all_steps if s.step_id == "list_materials"), None)
    if materials_step and materials_step.output_data:
        print(f"✅ list_materials 输出: {str(materials_step.output_data)[:80]}...")

    if ok:
        print("✅ DynamicWorkflow 端到端测试全部通过!")
    return ok


if __name__ == "__main__":
    success = asyncio.run(run_dynamic_workflow_test())
    sys.exit(0 if success else 1)
