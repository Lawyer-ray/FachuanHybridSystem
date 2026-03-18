"""Regression tests for CaseAdminService party projection helpers."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.cases.models import Case, CaseLogAttachment, CaseParty, SupervisingAuthority
from apps.cases.services.case.case_admin_service import CaseAdminService
from apps.contracts.models import ContractParty, FinalizedMaterial
from apps.testing.factories import CaseFactory, CaseLogFactory, ClientFactory, ClientIdentityDocFactory


class _MaterialServiceFake:
    def __init__(self) -> None:
        self.used_type_ids_calls: list[int] = []
        self.category_calls: list[tuple[str, int | None, tuple[int, ...]]] = []

    def get_used_type_ids(self, *, case_id: int) -> list[int]:
        self.used_type_ids_calls.append(case_id)
        return [1, 2]

    def get_material_types_by_category(
        self,
        *,
        category: str,
        law_firm_id: int | None,
        used_type_ids: list[int],
    ) -> list[dict[str, object]]:
        self.category_calls.append((category, law_firm_id, tuple(used_type_ids)))
        return [{"id": 100 if category == "party" else 200, "name": category}]


class _CaseImportServiceFake:
    def __init__(self, *, fail_names: set[str] | None = None) -> None:
        self.fail_names = fail_names or set()
        self.calls: list[dict[str, object]] = []

    def import_one(self, data: dict[str, object]) -> Case:
        self.calls.append(data)
        name = str(data.get("name") or "imported-case")
        if name in self.fail_names:
            raise ValueError("boom")
        return CaseFactory(name=name)


@pytest.mark.django_db
def test_case_admin_service_build_our_legal_entities_and_respondents() -> None:
    case = CaseFactory(name="projection-case")
    our_legal_client = ClientFactory(name="our-legal", is_our_client=True, client_type="legal")
    opponent_client = ClientFactory(name="opponent", is_our_client=False, client_type="legal")
    CaseParty.objects.create(case=case, client=our_legal_client, legal_status="plaintiff")
    CaseParty.objects.create(case=case, client=opponent_client, legal_status="defendant")

    service = CaseAdminService()

    our_legal_entities = service.build_our_legal_entities(case)
    respondents = service.build_respondents(case)

    assert our_legal_entities == [{"id": our_legal_client.id, "name": "our-legal"}]
    assert respondents == [{"id": opponent_client.id, "name": "opponent"}]


@pytest.mark.django_db
def test_case_admin_service_build_our_parties_preserves_fields() -> None:
    case = CaseFactory(name="projection-fields-case")
    our_client = ClientFactory(name="our-party", is_our_client=True, client_type="natural")
    CaseParty.objects.create(case=case, client=our_client, legal_status="plaintiff")

    service = CaseAdminService()
    parties = service.build_our_parties(case)

    assert len(parties) == 1
    assert parties[0]["id"] == our_client.id
    assert parties[0]["name"] == "our-party"
    assert parties[0]["client_type"] == "natural"
    assert parties[0]["legal_status"] == "plaintiff"
    assert parties[0]["legal_status_display"]


@pytest.mark.django_db
def test_case_admin_service_build_material_view_parties_preserves_fields() -> None:
    case = CaseFactory(name="material-parties-case")
    our_client = ClientFactory(name="our-material-party", is_our_client=True, client_type="legal")
    opponent_client = ClientFactory(name="opponent-material-party", is_our_client=False, client_type="natural")
    our_party = CaseParty.objects.create(case=case, client=our_client, legal_status="plaintiff")
    opponent_party = CaseParty.objects.create(case=case, client=opponent_client, legal_status="defendant")

    service = CaseAdminService()
    our_parties, opponent_parties = service.build_material_view_parties(case)

    assert our_parties == [
        {
            "id": our_party.id,
            "name": "our-material-party",
            "legal_status": "plaintiff",
            "legal_status_display": our_party.get_legal_status_display(),
        }
    ]
    assert opponent_parties == [
        {
            "id": opponent_party.id,
            "name": "opponent-material-party",
            "legal_status": "defendant",
            "legal_status_display": opponent_party.get_legal_status_display(),
        }
    ]


@pytest.mark.django_db
def test_case_admin_service_build_material_view_authorities_preserves_fields() -> None:
    case = CaseFactory(name="material-authorities-case")
    auth1 = SupervisingAuthority.objects.create(case=case, name="A", authority_type="trial")
    auth2 = SupervisingAuthority.objects.create(case=case, name="B", authority_type="investigation")

    service = CaseAdminService()
    authorities = service.build_material_view_authorities(case)

    assert [item["id"] for item in authorities] == [auth1.id, auth2.id]
    assert authorities[0]["name"] == "A"
    assert authorities[0]["authority_type"] == "trial"
    assert authorities[0]["authority_type_display"]


@pytest.mark.django_db
def test_case_admin_service_get_case_with_admin_relations_orders_logs_desc() -> None:
    case = CaseFactory(name="admin-relations-case")
    older_log = CaseLogFactory(case=case, content="older")
    newer_log = CaseLogFactory(case=case, content="newer")

    older_dt = timezone.now() - timedelta(days=1)
    newer_dt = timezone.now()
    type(older_log).objects.filter(pk=older_log.pk).update(created_at=older_dt)
    type(newer_log).objects.filter(pk=newer_log.pk).update(created_at=newer_dt)

    service = CaseAdminService()
    loaded_case = service.get_case_with_admin_relations(case.id)

    assert loaded_case is not None
    loaded_logs = list(loaded_case.logs.all())
    assert [log.id for log in loaded_logs] == [newer_log.id, older_log.id]


@pytest.mark.django_db
def test_case_admin_service_get_case_with_admin_relations_returns_none_for_missing_case() -> None:
    service = CaseAdminService()
    assert service.get_case_with_admin_relations(case_id=99999999) is None


@pytest.mark.django_db
def test_case_admin_service_build_materials_view_payload_preserves_structure() -> None:
    case = CaseFactory(name="materials-payload-case")
    our_client = ClientFactory(name="our-materials-payload", is_our_client=True, client_type="legal")
    opponent_client = ClientFactory(name="opponent-materials-payload", is_our_client=False, client_type="natural")
    our_party = CaseParty.objects.create(case=case, client=our_client, legal_status="plaintiff")
    opponent_party = CaseParty.objects.create(case=case, client=opponent_client, legal_status="defendant")
    authority = SupervisingAuthority.objects.create(case=case, name="Payload Authority", authority_type="trial")

    service = CaseAdminService()
    material_service = _MaterialServiceFake()
    payload = service.build_materials_view_payload(case=case, material_service=material_service, law_firm_id=7)

    assert material_service.used_type_ids_calls == [case.id]
    assert material_service.category_calls == [("party", 7, (1, 2)), ("non_party", 7, (1, 2))]
    assert payload["party_types"] == [{"id": 100, "name": "party"}]
    assert payload["non_party_types"] == [{"id": 200, "name": "non_party"}]
    assert payload["our_parties"] == [
        {
            "id": our_party.id,
            "name": "our-materials-payload",
            "legal_status": "plaintiff",
            "legal_status_display": our_party.get_legal_status_display(),
        }
    ]
    assert payload["opponent_parties"] == [
        {
            "id": opponent_party.id,
            "name": "opponent-materials-payload",
            "legal_status": "defendant",
            "legal_status_display": opponent_party.get_legal_status_display(),
        }
    ]
    assert payload["authorities"] == [
        {
            "id": authority.id,
            "name": "Payload Authority",
            "authority_type": "trial",
            "authority_type_display": authority.get_authority_type_display(),
        }
    ]


@pytest.mark.django_db
def test_case_admin_service_serialize_queryset_for_export_uses_contract_serializer_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = CaseFactory(name="service-export-case")
    calls: list[tuple[int, bool]] = []

    def _fake_contract_serializer(contract: object, *, case_serializer: object = None) -> dict[str, object]:
        assert hasattr(contract, "id")
        calls.append((int(contract.id), case_serializer is not None))
        return {"id": int(contract.id), "source": "service"}

    monkeypatch.setattr(
        "apps.contracts.services.contract.contract_export_serializer_service.serialize_contract_obj",
        _fake_contract_serializer,
    )

    service = CaseAdminService()
    data = service.serialize_queryset_for_export(Case.objects.filter(id=case.id))

    assert calls == [(case.contract_id, True)]
    assert data[0]["contract"] == {"id": case.contract_id, "source": "service"}


@pytest.mark.django_db
def test_case_admin_service_collect_file_paths_for_export_preserves_paths() -> None:
    case = CaseFactory(name="service-paths-case")
    FinalizedMaterial.objects.create(
        contract=case.contract,
        file_path="contracts/service-finalized.pdf",
        original_filename="service-finalized.pdf",
        category="other",
    )

    case_client = ClientFactory()
    CaseParty.objects.create(case=case, client=case_client, legal_status="plaintiff")
    ClientIdentityDocFactory(client=case_client, file_path="ids/service-case-client.pdf")

    contract_client = ClientFactory()
    ContractParty.objects.create(contract=case.contract, client=contract_client, role="PRINCIPAL")
    ClientIdentityDocFactory(client=contract_client, file_path="ids/service-contract-client.pdf")

    log = CaseLogFactory(case=case, content="service-path-log")
    attachment = CaseLogAttachment(log=log)
    attachment.file.save("service-log-attachment.pdf", ContentFile(b"content"), save=True)

    service = CaseAdminService()
    paths = service.collect_file_paths_for_export(Case.objects.filter(id=case.id))

    assert "contracts/service-finalized.pdf" in paths
    assert "ids/service-case-client.pdf" in paths
    assert "ids/service-contract-client.pdf" in paths


def test_case_admin_service_group_templates_by_sub_type_preserves_behavior() -> None:
    service = CaseAdminService()
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

    grouped = service.group_templates_by_sub_type(templates, sub_type_choices)

    assert grouped == [
        ("证据材料", [{"id": 3, "case_sub_type": "evidence_materials", "name": "keep-2"}]),
        ("其他材料", [{"id": 2, "case_sub_type": "other_materials", "name": "keep-1"}]),
    ]


def test_case_admin_service_detect_special_template_flags() -> None:
    service = CaseAdminService()
    unified_templates = [
        {"name": "财产保全申请书（模板）", "function_code": ""},
        {"name": "普通模板", "function_code": "delay_delivery_application"},
    ]

    has_preservation_template, has_delay_delivery_template = service.detect_special_template_flags(unified_templates)

    assert has_preservation_template is True
    assert has_delay_delivery_template is True


@pytest.mark.django_db
def test_case_admin_service_import_cases_from_json_data_counts_success_and_skipped() -> None:
    CaseFactory(name="existing-case", filing_number="FN-EXIST")
    service = CaseAdminService()
    fake_import = _CaseImportServiceFake()

    success, skipped, errors = service.import_cases_from_json_data(
        [
            {"name": "reuse-existing", "filing_number": "FN-EXIST"},
            {"name": "new-case", "filing_number": "FN-NEW"},
        ],
        case_import_service=fake_import,
    )

    assert success == 1
    assert skipped == 1
    assert errors == []
    assert len(fake_import.calls) == 2


@pytest.mark.django_db
def test_case_admin_service_import_cases_from_json_data_collects_error() -> None:
    service = CaseAdminService()
    fake_import = _CaseImportServiceFake(fail_names={"bad-case"})

    success, skipped, errors = service.import_cases_from_json_data(
        [{"name": "bad-case"}],
        case_import_service=fake_import,
    )

    assert success == 0
    assert skipped == 0
    assert len(errors) == 1
    assert "ValueError" in errors[0]
