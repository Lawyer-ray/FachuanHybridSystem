"""仓储层补测：CaseFullCreateRepo / CaseTemplateBindingRepo。"""

from __future__ import annotations

from uuid import uuid4

import pytest

from apps.cases.models import (
    BindingSource,
    CaseAssignment,
    CaseLog,
    CaseParty,
    CaseTemplateBinding,
    SupervisingAuthority,
)
from apps.cases.services.case.repo.case_full_create_repo import CaseFullCreateRepo
from apps.cases.services.template.repo import CaseTemplateBindingRepo
from apps.core.exceptions import NotFoundError
from apps.core.models.enums import AuthorityType
from apps.documents.models import DocumentTemplate
from apps.testing.factories import CaseFactory, ClientFactory, LawyerFactory


@pytest.mark.django_db
class TestCaseFullCreateRepo:
    def test_create_case_party_none_status_becomes_empty(self) -> None:
        case = CaseFactory()
        client = ClientFactory()
        party = CaseFullCreateRepo().create_case_party(case=case, client_id=client.id, legal_status=None)
        assert party.case_id == case.id
        assert party.client_id == client.id
        assert party.legal_status == ""

    def test_create_case_assignment(self) -> None:
        case = CaseFactory()
        lawyer = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")
        assignment = CaseFullCreateRepo().create_case_assignment(case=case, lawyer_id=lawyer.id)
        assert assignment.case_id == case.id
        assert assignment.lawyer_id == lawyer.id

    def test_create_case_log_with_event_date(self) -> None:
        case = CaseFactory()
        actor = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")
        log = CaseFullCreateRepo().create_case_log(
            case=case, content="日志内容", actor_id=actor.id, event_date="2026-10-01"
        )
        assert log.case_id == case.id
        assert str(log.event_date) == "2026-10-01"

    def test_create_case_log_without_event_date(self) -> None:
        case = CaseFactory()
        actor = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")
        log = CaseFullCreateRepo().create_case_log(case=case, content="日志内容", actor_id=actor.id, event_date=None)
        assert log.event_date is None

    def test_create_supervising_authority_none_defaults(self) -> None:
        case = CaseFactory()
        authority = CaseFullCreateRepo().create_supervising_authority(case=case, name=None, authority_type=None)
        assert authority.case_id == case.id
        assert authority.name == ""
        assert authority.authority_type == AuthorityType.TRIAL

    def test_bulk_create_case_parties(self) -> None:
        case = CaseFactory()
        clients = [ClientFactory(), ClientFactory()]
        repo = CaseFullCreateRepo()
        results = repo.bulk_create_case_parties(
            case=case,
            parties=[
                {"client_id": clients[0].id, "legal_status": "plaintiff"},
                {"client_id": clients[1].id},
            ],
        )
        assert len(results) == 2
        assert {p.legal_status for p in results} == {"plaintiff", ""}
        assert CaseParty.objects.filter(case=case).count() == 2

    def test_bulk_create_case_assignments(self) -> None:
        case = CaseFactory()
        lawyers = [
            LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}"),
            LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}"),
        ]
        results = CaseFullCreateRepo().bulk_create_case_assignments(
            case=case, assignments=[{"lawyer_id": lawyers[0].id}, {"lawyer_id": lawyers[1].id}]
        )
        assert len(results) == 2
        assert CaseAssignment.objects.filter(case=case).count() == 2

    def test_bulk_create_case_logs(self) -> None:
        case = CaseFactory()
        actor = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")
        results = CaseFullCreateRepo().bulk_create_case_logs(
            case=case,
            logs=[{"content": "日志一", "event_date": "2026-10-01"}, {"content": "日志二"}],
            actor_id=actor.id,
        )
        assert [log.content for log in results] == ["日志一", "日志二"]
        assert CaseLog.objects.filter(case=case).count() == 2

    def test_bulk_create_supervising_authorities(self) -> None:
        case = CaseFactory()
        results = CaseFullCreateRepo().bulk_create_supervising_authorities(
            case=case,
            authorities=[
                {"name": "法院A", "authority_type": AuthorityType.TRIAL},
                {},
            ],
        )
        assert [a.name for a in results] == ["法院A", ""]
        assert SupervisingAuthority.objects.filter(case=case).count() == 2


@pytest.mark.django_db
class TestCaseTemplateBindingRepo:
    def _make_case_with_template(self, *, name: str = "模板A", active: bool = True):
        case = CaseFactory()
        template = DocumentTemplate.objects.create(name=name, file_path=f"{name}.docx")
        if not active:
            template.is_active = False
            template.save(update_fields=["is_active"])
        return case, template

    def test_get_case_found(self) -> None:
        case = CaseFactory()
        assert CaseTemplateBindingRepo().get_case(case.id).id == case.id

    def test_get_case_missing_raises(self) -> None:
        with pytest.raises(NotFoundError) as exc_info:
            CaseTemplateBindingRepo().get_case(99999)
        assert exc_info.value.code == "CASE_NOT_FOUND"

    def test_get_case_optional(self) -> None:
        case = CaseFactory()
        repo = CaseTemplateBindingRepo()
        assert repo.get_case_optional(case.id).id == case.id
        assert repo.get_case_optional(99999) is None

    def test_get_bindings_by_case_id(self) -> None:
        case, template = self._make_case_with_template()
        other, other_template = self._make_case_with_template(name="模板B")
        CaseTemplateBinding.objects.create(case=case, template=template, binding_source=BindingSource.MANUAL_BOUND)
        CaseTemplateBinding.objects.create(case=other, template=other_template)

        bindings = CaseTemplateBindingRepo().get_bindings_by_case_id(case.id)

        assert [b.template_id for b in bindings] == [template.id]

    def test_get_binding_found_and_missing(self) -> None:
        case, template = self._make_case_with_template()
        binding = CaseTemplateBinding.objects.create(case=case, template=template)
        repo = CaseTemplateBindingRepo()

        assert repo.get_binding(case.id, binding.id).id == binding.id
        with pytest.raises(NotFoundError) as exc_info:
            repo.get_binding(case.id, binding.id + 99999)
        assert exc_info.value.code == "BINDING_NOT_FOUND"

    def test_exists_and_create_and_delete(self) -> None:
        case, template = self._make_case_with_template()
        repo = CaseTemplateBindingRepo()
        assert repo.exists_binding(case.id, template.id) is False

        binding = repo.create_binding(case.id, template.id, BindingSource.MANUAL_BOUND)
        assert repo.exists_binding(case.id, template.id) is True
        assert binding.binding_source == BindingSource.MANUAL_BOUND

        repo.delete_binding(binding)
        assert repo.exists_binding(case.id, template.id) is False

    def test_bound_auto_manual_template_ids(self) -> None:
        case, tpl_manual = self._make_case_with_template()
        tpl_auto = DocumentTemplate.objects.create(name="自动模板", file_path="auto.docx")
        CaseTemplateBinding.objects.create(case=case, template=tpl_manual, binding_source=BindingSource.MANUAL_BOUND)
        CaseTemplateBinding.objects.create(case=case, template=tpl_auto, binding_source=BindingSource.AUTO_RECOMMENDED)
        repo = CaseTemplateBindingRepo()

        assert repo.get_bound_template_ids(case.id) == {tpl_manual.id, tpl_auto.id}
        assert repo.get_auto_bound_template_ids(case.id) == {tpl_auto.id}
        assert repo.get_manual_bound_template_ids(case.id) == {tpl_manual.id}

    def test_delete_auto_bindings_only_removes_auto(self) -> None:
        case, tpl_manual = self._make_case_with_template()
        tpl_auto = DocumentTemplate.objects.create(name="自动模板", file_path="auto.docx")
        CaseTemplateBinding.objects.create(case=case, template=tpl_manual, binding_source=BindingSource.MANUAL_BOUND)
        CaseTemplateBinding.objects.create(case=case, template=tpl_auto, binding_source=BindingSource.AUTO_RECOMMENDED)
        repo = CaseTemplateBindingRepo()

        repo.delete_auto_bindings(case.id, {tpl_auto.id})
        repo.delete_auto_bindings(case.id, set())  # 空集合无操作

        assert repo.get_bound_template_ids(case.id) == {tpl_manual.id}

    def test_bulk_create_auto_bindings(self) -> None:
        case, _ = self._make_case_with_template()
        t1 = DocumentTemplate.objects.create(name="批量1", file_path="1.docx")
        t2 = DocumentTemplate.objects.create(name="批量2", file_path="2.docx")
        repo = CaseTemplateBindingRepo()

        repo.bulk_create_auto_bindings(case.id, set())
        repo.bulk_create_auto_bindings(case.id, {t1.id, t2.id})

        assert repo.get_auto_bound_template_ids(case.id) == {t1.id, t2.id}

    def test_get_our_legal_statuses(self) -> None:
        from apps.client.models import Client

        case = CaseFactory()
        our = Client.objects.create(name="我方", client_type=Client.NATURAL, is_our_client=True)
        other_our = Client.objects.create(name="我方二", client_type=Client.NATURAL, is_our_client=True)
        our_blank = Client.objects.create(name="我方三", client_type=Client.NATURAL, is_our_client=True)
        opponent = Client.objects.create(name="对方", client_type=Client.NATURAL, is_our_client=False)
        CaseParty.objects.create(case=case, client=our, legal_status="plaintiff")
        CaseParty.objects.create(case=case, client=other_our, legal_status="appellant")
        CaseParty.objects.create(case=case, client=opponent, legal_status="defendant")
        CaseParty.objects.create(case=case, client=our_blank, legal_status="")

        statuses = CaseTemplateBindingRepo().get_our_legal_statuses(case)

        assert set(statuses) == {"plaintiff", "appellant"}
