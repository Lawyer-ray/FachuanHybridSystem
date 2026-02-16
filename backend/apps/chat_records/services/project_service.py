"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from apps.chat_records.models import ChatRecordProject
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.security.admin_access import is_admin_user

from .access_policy import ensure_can_access_project


class ProjectService:
    def list_projects(self, *, user: Any | None) -> QuerySet[ChatRecordProject, ChatRecordProject]:
        qs = ChatRecordProject.objects.all()
        if not is_admin_user(user):
            qs = qs.filter(created_by=user)
        return qs.order_by("-created_at")

    def get_project(self, *, user: Any | None, project_id: int) -> ChatRecordProject:
        try:
            project = ChatRecordProject.objects.get(id=project_id)
        except ChatRecordProject.DoesNotExist:
            raise NotFoundError(f"项目 {project_id} 不存在") from None
        ensure_can_access_project(user=user, project=project)
        return project

    @transaction.atomic
    def create_project(self, *, name: str, description: str = "", created_by: Any | None = None) -> ChatRecordProject:
        if not name or not name.strip():
            raise ValidationException("项目名称不能为空")
        project = ChatRecordProject.objects.create(
            name=name.strip(),
            description=(description or "").strip(),
            created_by=created_by,
        )
        return project
