"""Regression tests for case_id inference in placeholder context builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.documents.services.placeholders.context_builder import EnhancedContextBuilder
from apps.documents.services.placeholders.litigation.enforcement_judgment_service import (
    EnforcementJudgmentMainTextService,
)
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys


@dataclass
class _CaseStub:
    id: int


class _CaptureCaseIdService:
    name = "capture_case_id_service"
    category = "test"
    placeholder_keys = ["captured_case_id"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        return {"captured_case_id": context_data.get("case_id")}


class _RegistryStub:
    def __init__(self, services: list[Any]) -> None:
        self._services = services

    def get_all_services(self) -> list[Any]:
        return self._services

    def get_service_for_placeholder(self, placeholder_key: str) -> Any | None:
        for service in self._services:
            if placeholder_key in getattr(service, "placeholder_keys", []):
                return service
        return None


def test_build_context_infers_case_id_from_case_object() -> None:
    builder = EnhancedContextBuilder(registry=_RegistryStub([_CaptureCaseIdService()]))

    context = builder.build_context({"case": _CaseStub(id=11)})

    assert context["captured_case_id"] == 11


def test_build_context_keeps_explicit_case_id() -> None:
    builder = EnhancedContextBuilder(registry=_RegistryStub([_CaptureCaseIdService()]))

    context = builder.build_context({"case": _CaseStub(id=11), "case_id": 99})

    assert context["captured_case_id"] == 99


def test_enforcement_judgment_service_infers_case_id_from_case_object() -> None:
    service = EnforcementJudgmentMainTextService()
    service.get_judgment_main_text = lambda case_id: f"main-{case_id}"  # type: ignore[method-assign]

    result = service.generate({"case": _CaseStub(id=11)})

    assert result[LitigationPlaceholderKeys.ENFORCEMENT_JUDGMENT_MAIN_TEXT] == "main-11"
