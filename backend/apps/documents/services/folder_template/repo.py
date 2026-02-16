"""Data repository layer."""

from collections.abc import Iterable
from typing import Any

from apps.documents.models import FolderTemplate


class FolderTemplateRepo:
    def create(self, **kwargs: Any) -> FolderTemplate:
        return FolderTemplate.objects.create(**kwargs)

    def get_by_id(self, template_id: int) -> FolderTemplate:
        return FolderTemplate.objects.get(id=template_id)

    def filter(self, **kwargs: Any) -> Iterable[FolderTemplate]:
        return FolderTemplate.objects.filter(**kwargs)

    def all(self) -> Iterable[FolderTemplate]:
        return FolderTemplate.objects.all()

    def get_optional(self, template_id: int) -> FolderTemplate | None | None:
        try:
            return FolderTemplate.objects.get(id=template_id)
        except FolderTemplate.DoesNotExist:
            return None
