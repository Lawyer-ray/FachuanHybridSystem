"""Module for forms."""

from __future__ import annotations

from typing import Any

from django import forms

from apps.documents.models import EvidenceList


class EvidenceListForm(forms.ModelForm[EvidenceList]):
    class Meta:
        model = EvidenceList
        fields: str = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        if "list_type" in self.fields:
            self.fields["list_type"].disabled = True


__all__: list[str] = ["EvidenceListForm"]
