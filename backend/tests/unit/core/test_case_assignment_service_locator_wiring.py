import pytest

from apps.core.service_locator_base import BaseServiceLocator
from apps.core.service_locator_mixins.business_mixin import BusinessServiceLocatorMixin


@pytest.mark.django_db
def test_case_assignment_service_locator_builds_with_deps():
    case_service = object()
    contract_assignment_query_service = object()

    class _DummyLocator(BaseServiceLocator, BusinessServiceLocatorMixin):
        _services = {}

        @classmethod
        def get_case_service(cls):
            return case_service

        @classmethod
        def get_contract_assignment_query_service(cls):
            return contract_assignment_query_service

    _DummyLocator.clear()
    service = _DummyLocator.get_case_assignment_service()

    from apps.cases.services import CaseAssignmentService

    assert isinstance(service, CaseAssignmentService)
    assert service._case_service is case_service
    assert service._contract_assignment_query_service is contract_assignment_query_service

