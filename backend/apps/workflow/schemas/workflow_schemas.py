"""工作流 Pydantic Schemas"""

from __future__ import annotations

from typing import Optional

from ninja import Schema


class StartWorkflowIn(Schema):
    template_slug: str
    case_id: int


class ApproveStepIn(Schema):
    approved: bool
    comment: str = ""


class StepExecutionOut(Schema):
    step_id: str
    name: str
    type: str
    status: str
    output_summary: str | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class WorkflowRunOut(Schema):
    run_id: int
    workflow_id: str
    template: str
    case_name: str
    status: str
    current_step: str
    started_at: str


class WorkflowDetailOut(Schema):
    run_id: int
    template: str
    case_name: str
    status: str
    current_step: str
    result: dict | None = None
    steps: list[StepExecutionOut]
    started_at: str
    finished_at: str | None = None


# ── 模板 CRUD Schemas ─────────────────────────────────────────────────────────


class StepConfigIn(Schema):
    """步骤配置输入"""
    id: str
    name: str
    type: str  # activity | gate | wait | condition | delay | llm | http | code
    description: str = ""
    icon: str = ""
    mcp_tool: str = ""
    config: dict = {}
    timeout: str = "30s"
    retry_max: int = 3
    on_fail: str = "abort"
    signal_key: str = ""
    # 用于 condition 类型
    condition_field: str = ""
    condition_operator: str = ""
    condition_value: str = ""
    # 用于编排器定位
    position_x: float = 0
    position_y: float = 0


class TemplateCreateIn(Schema):
    """创建模板输入"""
    name: str
    slug: str = ""
    category: str = "litigation"
    description: str = ""
    temporal_workflow_name: str = ""
    steps: list[StepConfigIn] = []
    is_active: bool = True


class TemplateUpdateIn(Schema):
    """更新模板输入"""
    name: str | None = None
    slug: str | None = None
    category: str | None = None
    description: str | None = None
    temporal_workflow_name: str | None = None
    steps: list[StepConfigIn] | None = None
    is_active: bool | None = None


class TemplateListOut(Schema):
    """模板列表输出"""
    id: int
    name: str
    slug: str
    category: str
    description: str
    is_active: bool
    steps_count: int
    temporal_workflow_name: str
    created_at: str
    updated_at: str


class TemplateDetailOut(Schema):
    """模板详情输出"""
    id: int
    name: str
    slug: str
    category: str
    description: str
    temporal_workflow_name: str
    steps_schema: list[dict] | dict
    is_active: bool
    created_at: str
    updated_at: str
