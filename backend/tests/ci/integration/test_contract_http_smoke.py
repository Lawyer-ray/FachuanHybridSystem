"""CI entry for reusable contract HTTP smoke tests."""

from __future__ import annotations

import pytest

from tests.ci.integration.contracts import test_contract_http_smoke as contract_http_smoke

contracts_admin_user = contract_http_smoke.contracts_admin_user
api_client = contract_http_smoke.api_client
BaseContractHttpSmoke = contract_http_smoke.TestContractHttpSmoke


@pytest.mark.django_db
@pytest.mark.integration
class TestContractHttpSmokeCI(BaseContractHttpSmoke):
    """Expose reusable contract smoke coverage to the CI test tree."""
