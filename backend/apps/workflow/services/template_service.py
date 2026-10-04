"""工作流模板服务 — 封装模板 CRUD、slug 唯一化与步骤白名单校验。

从 api/workflow_api.py 下沉（四层架构清偿：API 层只留工厂与参数提取）。
逻辑整体平移而非重写：响应 dict 字段名与中文文案是既有契约，前端依赖。
遵循 Service 层禁用静态方法装饰器的约定，工具函数写在模块级。
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.text import slugify

from apps.core.exceptions import NotFoundError, ValidationException
from apps.workflow.models import WorkflowTemplate
from apps.workflow.schemas.workflow_schemas import TemplateCreateIn, TemplateUpdateIn

logger = logging.getLogger(__name__)

# 危险步骤类型：code 的受限沙箱可被逃逸（见安全审计 A-01），http/mcp_tool 具有
# SSRF/越权能力，仅 superuser 可编排。种子模板只使用 activity/gate 等安全类型。
_FORBIDDEN_STEP_TYPES = {"code"}
_SUPERUSER_ONLY_STEP_TYPES = {"http", "mcp_tool"}


def _step_field(step: Any, field: str) -> str:
    """兼容 pydantic 模型与裸 dict 的步骤字段读取。"""
    if isinstance(step, dict):
        return str(step.get(field, "") or "")
    return str(getattr(step, field, "") or "")


def _template_summary(t: WorkflowTemplate) -> dict[str, Any]:
    """列表项序列化（契约冻结：字段名与 steps_count 行为与原 API 实现一致）。"""
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "category": t.category,
        "description": t.description,
        "is_active": t.is_active,
        "steps_count": len(t.steps_schema) if isinstance(t.steps_schema, list) else 0,
        "temporal_workflow_name": t.temporal_workflow_name,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


def _template_detail(t: WorkflowTemplate) -> dict[str, Any]:
    """详情序列化。"""
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "category": t.category,
        "description": t.description,
        "temporal_workflow_name": t.temporal_workflow_name,
        "steps_schema": t.steps_schema,
        "is_active": t.is_active,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


class WorkflowTemplateService:
    """工作流模板服务（sync；async 端点用 sync_to_async 包装调用）。"""

    def validate_steps_for_user(self, user: Any | None, steps: list[Any]) -> None:
        """模板步骤类型白名单校验（安全审计 A-01/B-01/B-02）。

        注意：执行器按 ``mcp_tool`` 字段存在性分发（workflows.py ``if mcp_tool:``），
        与 type 无关——因此任意类型步骤携带 mcp_tool 字段同样按超管限定处理。
        步骤项可以是 StepConfigIn 模型或存量模板中的裸 dict。
        """
        is_superuser = bool(user and getattr(user, "is_superuser", False))
        for step in steps or []:
            step_type = _step_field(step, "type").strip()
            if step_type in _FORBIDDEN_STEP_TYPES:
                raise ValidationException(
                    message=f"不允许使用步骤类型 {step_type}",
                    code="STEP_TYPE_FORBIDDEN",
                    errors={"type": step_type},
                )
            requires_superuser = step_type in _SUPERUSER_ONLY_STEP_TYPES
            if not requires_superuser and _step_field(step, "mcp_tool").strip():
                # 白名单绕过防护：type 合法但携带 mcp_tool 字段
                requires_superuser = True
            if requires_superuser and not is_superuser:
                raise ValidationException(
                    message="该步骤类型/配置仅超级管理员可用",
                    code="STEP_TYPE_REQUIRES_SUPERUSER",
                    errors={"type": step_type or "mcp_tool"},
                )

    def _unique_slug(self, base_slug: str, *, copy_mode: bool = False, exclude_pk: int | None = None) -> str:
        """slug 唯一化：普通模式 base[-N]；copy 模式 base-copy[-N]。

        exclude_pk 用于更新场景排除自身，避免"slug 未改名也被加后缀"。
        """
        slug = f"{base_slug}-copy" if copy_mode else base_slug
        counter = 1
        while self._slug_taken(slug, exclude_pk=exclude_pk):
            slug = f"{base_slug}-copy-{counter}" if copy_mode else f"{base_slug}-{counter}"
            counter += 1
        return slug

    def _slug_taken(self, slug: str, *, exclude_pk: int | None = None) -> bool:
        if exclude_pk is None:
            return WorkflowTemplate.objects.filter(slug=slug).exists()
        # 更新场景：排除自身，slug 未变化时不视为占用
        return WorkflowTemplate.objects.exclude(pk=exclude_pk).filter(slug=slug).exists()

    def list_templates(self, *, category: str | None = None, is_active: bool | None = None) -> list[dict[str, Any]]:
        qs = WorkflowTemplate.objects.all()
        if category:
            qs = qs.filter(category=category)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return [_template_summary(t) for t in qs]

    def get_template(self, template_id: int) -> dict[str, Any]:
        try:
            template = WorkflowTemplate.objects.get(pk=template_id)
        except WorkflowTemplate.DoesNotExist:
            raise NotFoundError(message=f"模板 #{template_id} 不存在", code="TEMPLATE_NOT_FOUND", errors={}) from None
        return _template_detail(template)

    def create_template(self, payload: TemplateCreateIn, *, user: Any | None = None) -> dict[str, Any]:
        self.validate_steps_for_user(user, payload.steps)
        slug = payload.slug or slugify(payload.name, allow_unicode=True)
        slug = self._unique_slug(slug)

        template = WorkflowTemplate.objects.create(
            name=payload.name,
            slug=slug,
            category=payload.category,
            description=payload.description,
            temporal_workflow_name=payload.temporal_workflow_name or "DynamicWorkflow",
            steps_schema=[s.model_dump() for s in payload.steps] if payload.steps else [],
            is_active=payload.is_active if payload.is_active is not None else True,
        )

        return {
            "id": template.id,
            "name": template.name,
            "slug": template.slug,
            "message": f"模板「{template.name}」创建成功",
        }

    def update_template(
        self, template_id: int, payload: TemplateUpdateIn, *, user: Any | None = None
    ) -> dict[str, Any]:
        try:
            template = WorkflowTemplate.objects.get(pk=template_id)
        except WorkflowTemplate.DoesNotExist:
            raise NotFoundError(message=f"模板 #{template_id} 不存在", code="TEMPLATE_NOT_FOUND", errors={}) from None

        if payload.name is not None:
            template.name = payload.name
        if payload.slug is not None:
            # slug 唯一化（与 create/duplicate 同口径）：撞车时自动加后缀而非 IntegrityError 500；
            # 排除自身，slug 未变化时不加后缀
            template.slug = self._unique_slug(payload.slug, exclude_pk=template.pk)
        if payload.category is not None:
            template.category = payload.category
        if payload.description is not None:
            template.description = payload.description
        if payload.temporal_workflow_name is not None:
            template.temporal_workflow_name = payload.temporal_workflow_name
        if payload.steps is not None:
            self.validate_steps_for_user(user, payload.steps)
            template.steps_schema = [s.model_dump() for s in payload.steps]
        if payload.is_active is not None:
            template.is_active = payload.is_active

        template.save()
        return {"id": template.id, "name": template.name, "message": "模板已更新"}

    def delete_template(self, template_id: int) -> dict[str, Any]:
        try:
            template = WorkflowTemplate.objects.get(pk=template_id)
        except WorkflowTemplate.DoesNotExist:
            raise NotFoundError(message=f"模板 #{template_id} 不存在", code="TEMPLATE_NOT_FOUND", errors={}) from None
        name = template.name
        template.delete()
        return {"message": f"模板「{name}」已删除"}

    def duplicate_template(self, template_id: int, *, user: Any | None = None) -> dict[str, Any]:
        try:
            source = WorkflowTemplate.objects.get(pk=template_id)
        except WorkflowTemplate.DoesNotExist:
            raise NotFoundError(message=f"模板 #{template_id} 不存在", code="TEMPLATE_NOT_FOUND", errors={}) from None

        # 复审结论：存量危险模板（修复前创建）不得经复制繁殖
        self.validate_steps_for_user(user, [s for s in (source.steps_schema or []) if isinstance(s, dict)])

        new_slug = self._unique_slug(source.slug, copy_mode=True)

        new_template = WorkflowTemplate.objects.create(
            name=f"{source.name} (副本)",
            slug=new_slug,
            category=source.category,
            description=source.description,
            temporal_workflow_name=source.temporal_workflow_name,
            steps_schema=source.steps_schema,
            is_active=False,
        )

        return {
            "id": new_template.id,
            "name": new_template.name,
            "slug": new_template.slug,
            "message": f"已复制为「{new_template.name}」",
        }


def get_workflow_template_service() -> WorkflowTemplateService:
    """工厂函数（测试锚点：可 patch 本函数替换服务实现）。"""
    return WorkflowTemplateService()
