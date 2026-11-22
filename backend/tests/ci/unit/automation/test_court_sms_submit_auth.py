"""P05-05 复核证据：`submit_sms` 并不是匿名端点。

审计报告断言它是「本 app 唯一无鉴权的写端点」。实际：`automation` 整个 router 在
`apiSystem/apiSystem/api.py` 里以 `auth=JWTOrSessionAuth()` 挂载，端点自身没有 `auth=None`
——匿名请求在进入视图前就被 401。本测试把这条结论钉死，防止将来有人加 `auth=None`。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_submit_sms_rejects_anonymous_request(client: Any) -> None:
    with patch("apps.core.dependencies.automation_sms_entry.build_court_sms_service_ctx") as mock_build:
        response = client.post(
            "/api/v1/automation/court-sms",
            data=json.dumps({"content": "【法院】匿名提交测试"}),
            content_type="application/json",
        )

    assert response.status_code == 401
    assert mock_build.call_count == 0
