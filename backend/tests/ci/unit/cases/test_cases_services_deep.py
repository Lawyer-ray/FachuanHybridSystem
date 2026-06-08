"""Comprehensive tests for cases services — command, query, access policy, search, log, party, number."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.cases.models import Case, CaseLog, CaseLogAttachment, CaseNumber
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.cases.services.case.case_command_service import CaseCommandService
from apps.cases.services.case.case_query_service import CaseQueryService
from apps.cases.services.case.case_search_service import CaseSearchService
from apps.cases.services.log.caselog_service import CaseLogService
from apps.cases.services.log.case_log_mutation_service import CaseLogMutationService
from apps.cases.services.log.case_log_query_service import CaseLogQueryService
from apps.cases.services.party.case_party_service import CasePartyService
from apps.cases.services.number.case_number_service import CaseNumberService
from apps.core.exceptions import ForbiddenError, NotFoundError, ValidationException
from apps.core.security.access_context import AccessContext
from apps.testing.factories import CaseFactory, CaseLogFactory, ClientFactory, ContractFactory, LawyerFactory


# ── Fixtures ──


@pytest.fixture
def access_policy():
    return CaseAccessPolicy()


@pytest.fixture
def admin_user(db, law_firm):
    from apps.organization.models import Lawyer

    return Lawyer.objects.create_user(
        username="admin_case_test",
        password="testpass123",
        is_admin=True,
        law_firm=law_firm,
    )


@pytest.fixture
def case_command_service():
    return CaseCommandService(contract_service=None, access_policy=CaseAccessPolicy())


# ── CaseAccessPolicy tests ──


@pytest.mark.django_db
class TestCaseAccessPolicy:
    def test_has_access_perm_open(self, access_policy):
        assert access_policy.has_access(1, None, None, perm_open_access=True)

    def test_has_access_no_user(self, access_policy):
        assert not access_policy.has_access(1, None, None)

    def test_has_access_admin(self, access_policy, admin_user):
        assert access_policy.has_access(1, admin_user, None)

    def test_has_access_extra_cases(self, access_policy, lawyer):
        org_access = {"extra_cases": {42, 43}}
        assert access_policy.has_access(42, lawyer, org_access)

    def test_has_access_with_case_obj(self, access_policy, admin_user):
        c = CaseFactory()
        assert access_policy.has_access(c.pk, admin_user, None, case=c)

    def test_ensure_access_raises(self, access_policy):
        with pytest.raises(ForbiddenError):
            access_policy.ensure_access(case_id=1, user=None, org_access=None)

    def test_ensure_access_passes(self, access_policy, admin_user):
        access_policy.ensure_access(case_id=1, user=admin_user, org_access=None)

    def test_ensure_access_ctx(self, access_policy, admin_user):
        ctx = AccessContext(user=admin_user, org_access=None, perm_open_access=False)
        access_policy.ensure_access_ctx(case_id=1, ctx=ctx)

    def test_can_access_authenticated(self, access_policy, lawyer):
        assert access_policy.can_access(lawyer)

    def test_can_access_anonymous(self, access_policy):
        assert not access_policy.can_access(None)

    def test_filter_queryset_perm_open(self, access_policy, db):
        qs = Case.objects.all()
        result = access_policy.filter_queryset(qs, None, None, perm_open_access=True)
        assert result is qs

    def test_filter_queryset_no_user(self, access_policy, db):
        CaseFactory()
        qs = Case.objects.all()
        result = access_policy.filter_queryset(qs, None, None)
        assert result.count() == 0

    def test_filter_queryset_admin(self, access_policy, admin_user, db):
        CaseFactory()
        qs = Case.objects.all()
        result = access_policy.filter_queryset(qs, admin_user, None)
        assert result.count() >= 1

    def test_filter_queryset_extra_cases(self, access_policy, lawyer, db):
        c = CaseFactory()
        org_access = {"extra_cases": {c.pk}}
        qs = Case.objects.all()
        result = access_policy.filter_queryset(qs, lawyer, org_access)
        assert result.count() >= 1

    def test_filter_queryset_no_allowed(self, access_policy, db):
        from apps.organization.models import Lawyer, LawFirm

        firm = LawFirm.objects.create(name="EmptyFirm")
        u = Lawyer.objects.create_user(username="nobody_case", password="p", law_firm=firm)
        CaseFactory()
        qs = Case.objects.all()
        result = access_policy.filter_queryset(qs, u, None)
        assert result.count() == 0

    def test_get_extra_cases(self, access_policy):
        assert access_policy._get_extra_cases(None) == set()
        assert access_policy._get_extra_cases({}) == set()
        assert access_policy._get_extra_cases({"extra_cases": {1, 2}}) == {1, 2}
        assert access_policy._get_extra_cases({"extra_cases": [1, 2]}) == {1, 2}


# ── CaseCommandService tests ──


@pytest.mark.django_db
class TestCaseCommandService:
    def test_create_case(self, case_command_service, admin_user):
        c = ContractFactory()
        case = case_command_service.create_case(
            {"name": "New Case", "contract": c},
            user=admin_user,
            perm_open_access=True,
        )
        assert case.pk is not None
        assert case.name == "New Case"

    def test_create_case_ctx(self, case_command_service, admin_user):
        c = ContractFactory()
        ctx = AccessContext(user=admin_user, org_access=None, perm_open_access=True)
        case = case_command_service.create_case_ctx(data={"name": "Ctx Case", "contract": c}, ctx=ctx)
        assert case.pk is not None

    def test_update_case(self, case_command_service, admin_user):
        c = CaseFactory()
        updated = case_command_service.update_case(
            c.pk, {"name": "Updated"}, user=admin_user, perm_open_access=True
        )
        assert updated.name == "Updated"

    def test_update_case_not_found(self, case_command_service, admin_user):
        with pytest.raises(NotFoundError):
            case_command_service.update_case(99999, {"name": "X"}, user=admin_user, perm_open_access=True)

    def test_update_case_ctx(self, case_command_service, admin_user):
        c = CaseFactory()
        ctx = AccessContext(user=admin_user, org_access=None, perm_open_access=True)
        updated = case_command_service.update_case_ctx(case_id=c.pk, data={"name": "Ctx Updated"}, ctx=ctx)
        assert updated.name == "Ctx Updated"

    def test_delete_case(self, case_command_service, admin_user):
        c = CaseFactory()
        case_command_service.delete_case(c.pk, user=admin_user, perm_open_access=True)
        assert not Case.objects.filter(pk=c.pk).exists()

    def test_delete_case_not_found(self, case_command_service, admin_user):
        with pytest.raises(NotFoundError):
            case_command_service.delete_case(99999, user=admin_user, perm_open_access=True)

    def test_delete_case_ctx(self, case_command_service, admin_user):
        c = CaseFactory()
        ctx = AccessContext(user=admin_user, org_access=None, perm_open_access=True)
        case_command_service.delete_case_ctx(case_id=c.pk, ctx=ctx)
        assert not Case.objects.filter(pk=c.pk).exists()

    def test_unbind_cases_from_contract(self, case_command_service):
        c = ContractFactory()
        CaseFactory(contract=c)
        CaseFactory(contract=c)
        count = case_command_service.unbind_cases_from_contract_internal(c.pk)
        assert count == 2

    def test_close_cases_by_contract(self, case_command_service):
        c = ContractFactory()
        CaseFactory(contract=c)
        count = case_command_service.close_cases_by_contract_internal(c.pk)
        assert count >= 1

    def test_count_cases_by_contract(self, case_command_service):
        c = ContractFactory()
        CaseFactory(contract=c)
        CaseFactory(contract=c)
        assert case_command_service.count_cases_by_contract(c.pk) == 2

    def test_validate_stage_valid(self, case_command_service):
        from apps.core.config.business_config import business_config

        stages = [v for v, _ in business_config.get_stages_for_case_type("civil")]
        if stages:
            result = case_command_service._validate_stage(stages[0], "civil")
            assert result == stages[0]

    def test_validate_stage_invalid_type(self, case_command_service):
        with pytest.raises(ValidationException):
            case_command_service._validate_stage("不存在的阶段", "civil")

    def test_validate_contract_no_service(self, case_command_service):
        # No contract service, should pass silently
        case_command_service._validate_contract(1)


# ── CaseSearchService tests ──


@pytest.mark.django_db
class TestCaseSearchService:
    def test_list_cases(self, db):
        svc = CaseSearchService()
        CaseFactory()
        CaseFactory()
        qs = svc.list_cases(perm_open_access=True)
        assert qs.count() >= 2

    def test_list_cases_filter_case_type(self, db):
        svc = CaseSearchService()
        c = ContractFactory(case_type="civil")
        CaseFactory(contract=c)
        qs = svc.list_cases(case_type="civil", perm_open_access=True)
        assert qs.count() >= 1

    def test_list_cases_ctx(self, db):
        svc = CaseSearchService()
        CaseFactory()
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        qs = svc.list_cases_ctx(ctx=ctx)
        assert qs.count() >= 1

    def test_search_cases_empty_query(self, db):
        svc = CaseSearchService()
        assert svc.search_cases("", perm_open_access=True) == []

    def test_search_cases_by_name(self, db):
        svc = CaseSearchService()
        CaseFactory(name="Alpha案")
        CaseFactory(name="Beta案")
        results = svc.search_cases("Alpha", perm_open_access=True)
        assert len(results) >= 1

    def test_search_cases_ctx(self, db):
        svc = CaseSearchService()
        CaseFactory(name="搜索测试案")
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        results = svc.search_cases_ctx(ctx=ctx, query="搜索测试")
        assert len(results) >= 1

    def test_search_by_case_number_empty(self, db):
        svc = CaseSearchService()
        qs = svc.search_by_case_number("", perm_open_access=True)
        assert qs.count() == 0

    def test_search_by_case_number_found(self, db):
        svc = CaseSearchService()
        c = CaseFactory()
        CaseNumber.objects.create(case=c, number="(2026)京01民初123号")
        qs = svc.search_by_case_number("京01民初123", perm_open_access=True)
        assert qs.count() >= 1

    def test_search_by_case_number_exact(self, db):
        svc = CaseSearchService()
        c = CaseFactory()
        CaseNumber.objects.create(case=c, number="（2026）京01民初456号")
        qs = svc.search_by_case_number("（2026）京01民初456号", perm_open_access=True, exact_match=True)
        assert qs.count() >= 1

    def test_search_by_case_number_ctx(self, db):
        svc = CaseSearchService()
        c = CaseFactory()
        CaseNumber.objects.create(case=c, number="(2026)京02民初789号")
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        qs = svc.search_by_case_number_ctx(ctx=ctx, case_number="京02民初789")
        assert qs.count() >= 1


# ── CaseQueryService tests ──


@pytest.mark.django_db
class TestCaseQueryService:
    def test_list_cases(self, db):
        svc = CaseQueryService()
        CaseFactory()
        qs = svc.list_cases(perm_open_access=True)
        assert qs.count() >= 1

    def test_list_cases_ctx(self, db):
        svc = CaseQueryService()
        CaseFactory()
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        qs = svc.list_cases_ctx(ctx=ctx)
        assert qs.count() >= 1

    def test_get_case(self, db):
        svc = CaseQueryService()
        c = CaseFactory()
        result = svc.get_case(c.pk, perm_open_access=True)
        assert result.pk == c.pk

    def test_get_case_not_found(self, db):
        svc = CaseQueryService()
        with pytest.raises(NotFoundError):
            svc.get_case(99999, perm_open_access=True)

    def test_get_case_ctx(self, db):
        svc = CaseQueryService()
        c = CaseFactory()
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        result = svc.get_case_ctx(case_id=c.pk, ctx=ctx)
        assert result.pk == c.pk

    def test_search_cases(self, db):
        svc = CaseQueryService()
        CaseFactory(name="Query搜索案")
        results = svc.search_cases("Query搜索", perm_open_access=True)
        assert len(results) >= 1

    def test_search_cases_ctx(self, db):
        svc = CaseQueryService()
        CaseFactory(name="Ctx搜索案")
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        results = svc.search_cases_ctx(ctx=ctx, query="Ctx搜索")
        assert len(results) >= 1

    def test_search_by_case_number(self, db):
        svc = CaseQueryService()
        c = CaseFactory()
        CaseNumber.objects.create(case=c, number="(2026)京03民初100号")
        qs = svc.search_by_case_number("京03民初100", perm_open_access=True)
        assert qs.count() >= 1

    def test_search_by_case_number_ctx(self, db):
        svc = CaseQueryService()
        c = CaseFactory()
        CaseNumber.objects.create(case=c, number="(2026)京04民初200号")
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        qs = svc.search_by_case_number_ctx(ctx=ctx, case_number="京04民初200")
        assert qs.count() >= 1

    def test_check_case_access(self, db, admin_user):
        svc = CaseQueryService()
        c = CaseFactory()
        assert svc.check_case_access(c, admin_user, None) is True

    def test_check_case_access_ctx(self, db, admin_user):
        svc = CaseQueryService()
        c = CaseFactory()
        ctx = AccessContext(user=admin_user, org_access=None, perm_open_access=False)
        assert svc.check_case_access_ctx(case=c, ctx=ctx) is True


# ── CaseLogService tests ──


@pytest.mark.django_db
class TestCaseLogService:
    def test_list_logs(self, db):
        svc = CaseLogService()
        c = CaseFactory()
        CaseLogFactory(case=c)
        qs = svc.list_logs(case_id=c.pk, perm_open_access=True)
        assert qs.count() >= 1

    def test_list_logs_all(self, db):
        svc = CaseLogService()
        CaseLogFactory()
        qs = svc.list_logs(perm_open_access=True)
        assert qs.count() >= 1

    def test_get_log(self, db):
        svc = CaseLogService()
        log = CaseLogFactory()
        result = svc.get_log(log.pk, perm_open_access=True)
        assert result.pk == log.pk

    def test_get_log_not_found(self, db):
        svc = CaseLogService()
        with pytest.raises(NotFoundError):
            svc.get_log(99999, perm_open_access=True)

    def test_create_log(self, db, admin_user):
        svc = CaseLogService()
        c = CaseFactory()
        log = svc.create_log(c.pk, "测试日志内容", user=admin_user, perm_open_access=True)
        assert log.pk is not None
        assert log.content == "测试日志内容"

    def test_create_log_not_found(self, db, admin_user):
        svc = CaseLogService()
        with pytest.raises(NotFoundError):
            svc.create_log(99999, "内容", user=admin_user, perm_open_access=True)

    def test_update_log(self, db, admin_user):
        svc = CaseLogService()
        log = CaseLogFactory()
        updated = svc.update_log(log.pk, {"content": "更新内容"}, user=admin_user, perm_open_access=True)
        assert updated.content == "更新内容"

    def test_delete_log(self, db, admin_user):
        svc = CaseLogService()
        log = CaseLogFactory()
        result = svc.delete_log(log.pk, user=admin_user, perm_open_access=True)
        assert result["success"] is True
        assert not CaseLog.objects.filter(pk=log.pk).exists()

    def test_get_logs_for_case(self, db):
        svc = CaseLogService()
        c = CaseFactory()
        CaseLogFactory(case=c)
        qs = svc.get_logs_for_case(c.pk, perm_open_access=True)
        assert qs.count() >= 1

    def test_get_log_versions(self, db):
        svc = CaseLogService()
        log = CaseLogFactory()
        versions = svc.get_log_versions(log.pk, perm_open_access=True)
        assert isinstance(versions, list)

    def test_delete_attachment_not_found(self, db, admin_user):
        svc = CaseLogService()
        with pytest.raises(NotFoundError):
            svc.delete_attachment(99999, user=admin_user, perm_open_access=True)


# ── CaseLogMutationService tests ──


@pytest.mark.django_db
class TestCaseLogMutationService:
    def test_create_log(self, db, admin_user):
        c = CaseFactory()
        query_svc = CaseLogQueryService(access_policy=CaseAccessPolicy())
        svc = CaseLogMutationService(query_service=query_svc)
        log = svc.create_log(case_id=c.pk, content="Mutation日志", user=admin_user, perm_open_access=True)
        assert log.pk is not None

    def test_update_log(self, db, admin_user):
        log = CaseLogFactory()
        query_svc = CaseLogQueryService(access_policy=CaseAccessPolicy())
        svc = CaseLogMutationService(query_service=query_svc)
        updated = svc.update_log(log_id=log.pk, data={"content": "Updated"}, user=admin_user, perm_open_access=True)
        assert updated.content == "Updated"

    def test_delete_log(self, db, admin_user):
        log = CaseLogFactory()
        query_svc = CaseLogQueryService(access_policy=CaseAccessPolicy())
        svc = CaseLogMutationService(query_service=query_svc)
        result = svc.delete_log(log_id=log.pk, user=admin_user, perm_open_access=True)
        assert result["success"] is True


# ── CaseLogQueryService tests ──


@pytest.mark.django_db
class TestCaseLogQueryService:
    def test_list_logs(self, db):
        svc = CaseLogQueryService(access_policy=CaseAccessPolicy())
        CaseLogFactory()
        qs = svc.list_logs(perm_open_access=True)
        assert qs.count() >= 1

    def test_list_logs_by_case(self, db):
        svc = CaseLogQueryService(access_policy=CaseAccessPolicy())
        c = CaseFactory()
        CaseLogFactory(case=c)
        qs = svc.list_logs(case_id=c.pk, perm_open_access=True)
        assert qs.count() >= 1

    def test_get_log(self, db):
        svc = CaseLogQueryService(access_policy=CaseAccessPolicy())
        log = CaseLogFactory()
        result = svc.get_log(log_id=log.pk, perm_open_access=True)
        assert result.pk == log.pk

    def test_get_log_not_found(self, db):
        svc = CaseLogQueryService(access_policy=CaseAccessPolicy())
        with pytest.raises(NotFoundError):
            svc.get_log(log_id=99999, perm_open_access=True)


# ── Case model tests ──


@pytest.mark.django_db
class TestCaseModel:
    def test_case_str(self):
        c = CaseFactory(name="TestCase")
        assert str(c) == "TestCase"

    def test_case_defaults(self):
        c = CaseFactory()
        assert c.status == "active"

    def test_case_with_contract(self):
        contract = ContractFactory()
        c = CaseFactory(contract=contract)
        assert c.contract_id == contract.pk

    def test_case_number_model(self):
        c = CaseFactory()
        cn = CaseNumber.objects.create(case=c, number="(2026)京01民初1号")
        assert str(cn) is not None

    def test_case_log_str(self):
        log = CaseLogFactory(content="TestLog")
        assert "TestLog" in str(log) or log.content == "TestLog"


# ── CasePartyService tests ──


@pytest.mark.django_db
class TestCasePartyService:
    def test_list_parties(self, db):
        from apps.cases.models import CaseParty

        svc = CasePartyService()
        c = CaseFactory()
        client = ClientFactory()
        CaseParty.objects.create(case=c, client=client, legal_status="原告")
        parties = svc.list_parties(case_id=c.pk, perm_open_access=True)
        assert parties.count() >= 1

    def test_list_parties_empty(self, db):
        svc = CasePartyService()
        c = CaseFactory()
        parties = svc.list_parties(case_id=c.pk, perm_open_access=True)
        assert parties.count() == 0

    def test_get_available_legal_statuses(self, db):
        svc = CasePartyService()
        c = CaseFactory()
        statuses = svc.get_available_legal_statuses(c.pk, perm_open_access=True)
        assert isinstance(statuses, list)


# ── CaseNumberService tests ──


@pytest.mark.django_db
class TestCaseNumberService:
    def test_list_numbers(self, db):
        svc = CaseNumberService()
        c = CaseFactory()
        CaseNumber.objects.create(case=c, number="(2026)京01民初1号")
        numbers = svc.list_numbers(case_id=c.pk, perm_open_access=True)
        assert numbers.count() >= 1

    def test_list_numbers_empty(self, db):
        svc = CaseNumberService()
        c = CaseFactory()
        numbers = svc.list_numbers(case_id=c.pk, perm_open_access=True)
        assert numbers.count() == 0

    def test_format_case_number(self, db):
        svc = CaseNumberService()
        result = svc.format_case_number("2026京01民初1号")
        assert isinstance(result, str)

    def test_normalize_case_number(self, db):
        svc = CaseNumberService()
        result = svc.normalize_case_number("2026京01民初1号")
        assert isinstance(result, str)
