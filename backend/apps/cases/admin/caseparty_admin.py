from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import URLPattern, path

from apps.cases.models import CaseParty


@admin.register(CaseParty)
class CasePartyAdmin(admin.ModelAdmin[CaseParty]):
    list_display = ("id", "case", "client", "is_our_client", "legal_status")
    list_filter = ("legal_status",)
    search_fields = ("case__name", "client__name")

    def is_our_client(self, obj: CaseParty) -> bool:
        return bool(getattr(obj.client, "is_our_client", False))

    is_our_client.boolean = True  # type: ignore[attr-defined]
    is_our_client.short_description = "是否为我方当事人"  # type: ignore[attr-defined]

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom: list[URLPattern] = [
            path(
                "is-our-client/<int:client_id>/",
                self.admin_site.admin_view(self.is_our_client_view),
                name="cases_caseparty_is_our_client",
            ),
        ]
        return custom + urls

    def is_our_client_view(self, request: HttpRequest, client_id: int) -> JsonResponse:
        from apps.core.interfaces import ServiceLocator

        client_service = ServiceLocator.get_client_service()
        client_dto = client_service.get_client(client_id)
        val = bool(client_dto.is_our_client) if client_dto else False
        return JsonResponse({"is_our_client": val})
