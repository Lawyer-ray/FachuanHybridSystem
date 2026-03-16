"""Regression guards for case admin export paths."""

from __future__ import annotations

import inspect

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.files.base import ContentFile

from apps.cases.admin.case_admin import CaseAdmin
from apps.cases.admin.mixins.views import CaseAdminViewsMixin
from apps.cases.models import Case, CaseLogAttachment, CaseParty
from apps.cases.services.case.case_admin_export_bridge import (
    collect_case_file_paths_for_export,
    get_case_admin_export_prefetches,
    get_case_admin_file_prefetches,
)
from apps.cases.services.case.case_contract_export_bridge import (
    collect_contract_file_paths_for_case_export,
    get_case_admin_contract_export_prefetches,
    get_case_admin_contract_file_prefetches,
)
from apps.contracts.models import ContractParty, FinalizedMaterial
from tests.factories import CaseFactory, CaseLogFactory, ClientFactory, ClientIdentityDocFactory


@pytest.mark.django_db
def test_case_admin_serialize_queryset_uses_contract_serializer_service(monkeypatch: pytest.MonkeyPatch) -> None:
    case = CaseFactory(name="bridge-case")
    calls: list[tuple[int, bool]] = []

    def _fake_contract_serializer(contract: object, *, case_serializer: object = None) -> dict[str, object]:
        assert hasattr(contract, "id")
        calls.append((int(contract.id), case_serializer is not None))
        return {"id": int(contract.id), "source": "service"}

    monkeypatch.setattr(
        "apps.contracts.services.contract.contract_export_serializer_service.serialize_contract_obj",
        _fake_contract_serializer,
    )

    admin_obj = CaseAdmin(Case, AdminSite())
    data = admin_obj.serialize_queryset(Case.objects.filter(id=case.id))

    assert calls == [(case.contract_id, True)]
    assert data[0]["contract"] == {"id": case.contract_id, "source": "service"}


@pytest.mark.django_db
def test_case_admin_get_file_paths_preserves_exported_paths() -> None:
    case = CaseFactory(name="paths-case")
    FinalizedMaterial.objects.create(
        contract=case.contract,
        file_path="contracts/finalized.pdf",
        original_filename="finalized.pdf",
        category="other",
    )

    case_client = ClientFactory()
    CaseParty.objects.create(case=case, client=case_client, legal_status="plaintiff")
    ClientIdentityDocFactory(client=case_client, file_path="ids/case-client.pdf")

    contract_client = ClientFactory()
    ContractParty.objects.create(contract=case.contract, client=contract_client, role="PRINCIPAL")
    ClientIdentityDocFactory(client=contract_client, file_path="ids/contract-client.pdf")

    log = CaseLogFactory(case=case, content="path-log")
    attachment = CaseLogAttachment(log=log)
    attachment.file.save("log-attachment.pdf", ContentFile(b"content"), save=True)

    admin_obj = CaseAdmin(Case, AdminSite())
    paths = admin_obj.get_file_paths(Case.objects.filter(id=case.id))

    assert "contracts/finalized.pdf" in paths
    assert "ids/case-client.pdf" in paths
    assert "ids/contract-client.pdf" in paths


@pytest.mark.django_db
def test_client_identity_doc_str_remains_hidden() -> None:
    identity_doc = ClientIdentityDocFactory(file_path="ids/hidden-str.pdf")
    assert str(identity_doc) == ""


def test_case_admin_serialize_queryset_does_not_prefetch_reminders_reverse_relation() -> None:
    source = inspect.getsource(CaseAdmin.serialize_queryset)
    assert "logs__reminders" not in source
    assert "contract__reminders" not in source
    assert "apps.contracts.services" not in source


def test_case_admin_views_does_not_prefetch_case_log_reminders_reverse_relation() -> None:
    source = inspect.getsource(CaseAdminViewsMixin._get_case_with_relations)
    assert '"reminders"' not in source


def test_case_admin_views_group_templates_by_sub_type_preserves_behavior() -> None:
    templates = [
        {"id": 1, "case_sub_type": "power_of_attorney_materials", "name": "skip-1"},
        {"id": 2, "case_sub_type": "other_materials", "name": "keep-1"},
        {"id": 3, "case_sub_type": "evidence_materials", "name": "keep-2"},
        {"id": 4, "case_sub_type": "property_preservation_materials", "name": "skip-2"},
    ]
    sub_type_choices = [
        ("pleading_materials", "诉状材料"),
        ("evidence_materials", "证据材料"),
        ("other_materials", "其他材料"),
    ]

    grouped = CaseAdminViewsMixin._group_templates_by_sub_type(templates, sub_type_choices)

    assert grouped == [
        ("证据材料", [{"id": 3, "case_sub_type": "evidence_materials", "name": "keep-2"}]),
        ("其他材料", [{"id": 2, "case_sub_type": "other_materials", "name": "keep-1"}]),
    ]


def test_case_admin_views_has_no_direct_documents_choices_import() -> None:
    source = inspect.getsource(CaseAdminViewsMixin._group_templates_by_sub_type)
    assert "apps.documents.models.choices" not in source


def test_case_contract_export_bridge_exposes_contract_prefetch_paths() -> None:
    assert "contract__finalized_materials" in get_case_admin_contract_export_prefetches()
    assert "contract__payments__invoices" in get_case_admin_contract_export_prefetches()
    assert "contract__contract_parties__client__identity_docs" in get_case_admin_contract_file_prefetches()


def test_case_admin_export_bridge_exposes_case_prefetch_paths() -> None:
    assert "parties__client__identity_docs" in get_case_admin_export_prefetches()
    assert "logs__actor" in get_case_admin_export_prefetches()
    assert "logs__attachments" in get_case_admin_file_prefetches()


@pytest.mark.django_db
def test_case_admin_export_bridge_collects_case_file_paths() -> None:
    case = CaseFactory(name="case-bridge-paths-case")
    case_client = ClientFactory()
    CaseParty.objects.create(case=case, client=case_client, legal_status="plaintiff")
    ClientIdentityDocFactory(client=case_client, file_path="ids/case-bridge-client.pdf")

    log = CaseLogFactory(case=case, content="bridge-log")
    attachment = CaseLogAttachment(log=log)
    attachment.file.save("case-bridge-log.pdf", ContentFile(b"content"), save=True)

    paths: list[str] = []
    collect_case_file_paths_for_export(case, paths.append)

    assert "ids/case-bridge-client.pdf" in paths
    assert any("case-bridge-log" in path for path in paths)


@pytest.mark.django_db
def test_case_contract_export_bridge_collects_contract_file_paths() -> None:
    case = CaseFactory(name="bridge-paths-case")
    contract_client = ClientFactory()
    ContractParty.objects.create(contract=case.contract, client=contract_client, role="PRINCIPAL")
    ClientIdentityDocFactory(client=contract_client, file_path="ids/contract-bridge-client.pdf")
    FinalizedMaterial.objects.create(
        contract=case.contract,
        file_path="contracts/bridge-finalized.pdf",
        original_filename="bridge-finalized.pdf",
        category="other",
    )

    paths: list[str] = []
    collect_contract_file_paths_for_case_export(case.contract, paths.append)

    assert "contracts/bridge-finalized.pdf" in paths
    assert "ids/contract-bridge-client.pdf" in paths
