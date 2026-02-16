"""Data repository layer."""

from __future__ import annotations

from typing import Any

from apps.documents.models import DocumentTemplate


class DocumentTemplateRepo:
    def create(self, **kwargs: Any) -> DocumentTemplate:
        return DocumentTemplate.objects.create(**kwargs)

    def get_by_id(self, template_id: int) -> DocumentTemplate:
        return DocumentTemplate.objects.get(id=template_id)

    def get_optional(self, template_id: int) -> DocumentTemplate | None | None:
        try:
            return DocumentTemplate.objects.get(id=template_id)
        except DocumentTemplate.DoesNotExist:
            return None

    def all(self) -> Any:
        return DocumentTemplate.objects.all()

    def filter(self, **kwargs: Any) -> Any:
        return DocumentTemplate.objects.filter(**kwargs)
