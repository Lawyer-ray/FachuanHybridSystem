"""contracts API 创建权限对齐测试（安全审计）。

POST /contracts 与 /contracts/full 同样在入口校验 can_create_contract，
未通过时返回 403（PERMISSION_DENIED），不再依赖 service 层兜底。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _request(user: object) -> SimpleNamespace:
    return SimpleNamespace(user=user, org_access=None, perm_open_access=False)


@pytest.mark.asyncio
async def test_create_contract_denied_without_permission() -> None:
    """can_create_contract=False 时 POST /contracts 直接 403。"""
    from apps.contracts.api import contract_api
    from apps.core.exceptions import PermissionDenied

    payload = MagicMock()
    payload.model_dump.return_value = {"name": "无权合同", "case_type": "civil"}

    policy = MagicMock()
    policy.can_create_contract.return_value = False
    mock_service = MagicMock()

    with (
        patch.object(contract_api, "_get_domain_service", return_value=mock_service),
        patch.object(contract_api, "_get_access_policy", return_value=policy),
        patch.object(contract_api, "extract_request_context", return_value=SimpleNamespace(user=None)),
    ):
        with pytest.raises(PermissionDenied):
            await contract_api.create_contract(_request(user=None), payload)

    mock_service.create_contract_with_cases.assert_not_called()


@pytest.mark.asyncio
async def test_create_contract_full_endpoint_untouched() -> None:
    """/full 入口同样拦截（既有行为，回归保护）。"""
    from apps.contracts.api import contract_api
    from apps.core.exceptions import PermissionDenied

    payload = MagicMock()
    payload.model_dump.return_value = {"name": "无权合同2", "case_type": "civil", "cases": None}

    policy = MagicMock()
    policy.can_create_contract.return_value = False
    mock_service = MagicMock()

    with (
        patch.object(contract_api, "_get_domain_service", return_value=mock_service),
        patch.object(contract_api, "_get_access_policy", return_value=policy),
        patch.object(contract_api, "extract_request_context", return_value=SimpleNamespace(user=None)),
    ):
        with pytest.raises(PermissionDenied):
            await contract_api.create_contract_with_cases(_request(user=None), payload)

    mock_service.create_contract_with_cases.assert_not_called()
