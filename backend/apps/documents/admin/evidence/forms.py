"""Module for forms."""

from django import forms

from apps.documents.models import EvidenceList


class EvidenceListForm(forms.ModelForm):
    class Meta:
        model = EvidenceList
        fields: str = "__all__"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        if "list_type" in self.fields:
            self.fields["list_type"].disabled = True


__all__: list[str] = ["EvidenceListForm"]
