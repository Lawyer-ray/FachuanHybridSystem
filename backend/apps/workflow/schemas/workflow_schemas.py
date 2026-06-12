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
