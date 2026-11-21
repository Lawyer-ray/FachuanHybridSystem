"""归档两个整批写端点的多栏兜底（入口 C）。

`generate-folder` / `sync-case-materials` 会**重建绑定目录里的整批文件**，多栏并答
时直接调它就是替其它栏把文件全部盖掉。三个口径：

1. 带会话头 + 该会话多栏登记 → 409，且权限校验/生成服务一步都没跑；
2. 带会话头 + 单栏 → 放行到正常流程（这里权限校验返回「合同不存在」→ 404）；
3. 不带会话头 → 放行（律师在页面上点「生成归档目录」）。

放行的证据用「`_ensure_contract_access` 被 await 过一次」：拒写发生在它之前，
所以被拦时它一次都不该被调用。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from django.test import Client as DjangoTestClient

from apps.agent.services.approval.policy import clear_multi_lane_session, mark_multi_lane_session
from apps.agent.services.approval.write_guard import MULTI_LANE_WRITE_CODE

# 端点挂在 JWTOrSessionAuth 下：会话登录与中间件的 statement_timeout 都要连库
pytestmark = pytest.mark.django_db(transaction=True)

GENERATE_URL = "/api/v1/contracts/1/archive/generate-folder"
SYNC_URL = "/api/v1/contracts/1/archive/sync-case-materials"
MULTI = "archive-multi-lane"
SINGLE = "archive-single-lane"


@pytest.fixture
def client() -> DjangoTestClient:
    """已登录律师的客户端：端点挂在 JWTOrSessionAuth 下，匿名会被 401 挡住。"""
    from apps.testing.factories import LawyerFactory

    c = DjangoTestClient()
    c.force_login(LawyerFactory())
    return c


@pytest.fixture
def multi_session() -> Any:
    mark_multi_lane_session(MULTI)
    try:
        yield MULTI
    finally:
        clear_multi_lane_session(MULTI)


@pytest.fixture
def single_session() -> Any:
    mark_multi_lane_session(SINGLE)
    clear_multi_lane_session(SINGLE)
    return SINGLE


def _access_check(return_value: Any = None) -> AsyncMock:
    """`_ensure_contract_access` 的替身；返回 None = 合同不存在（调用方按 404 处理）。"""
    return AsyncMock(return_value=return_value)


class TestGenerateArchiveFolder:
    def test_multi_lane_agent_is_refused_before_any_work(self, client: DjangoTestClient, multi_session: str) -> None:
        ensure = _access_check()
        with patch("apps.contracts.api.archive_api._ensure_contract_access", ensure):
            resp = client.post(GENERATE_URL, headers={"x-fachuan-session": multi_session})

        assert resp.status_code == 409, resp.content
        body = resp.json()
        assert body["code"] == MULTI_LANE_WRITE_CODE
        assert "propose_write_patch" in body["message"]
        assert body["errors"]["endpoint"] == "contracts.archive.generate_folder"
        # 拒写在权限校验与生成服务之前：一步都没跑，更谈不上写盘
        ensure.assert_not_awaited()

    def test_single_lane_agent_passes_the_guard(self, client: DjangoTestClient, single_session: str) -> None:
        ensure = _access_check()
        with patch("apps.contracts.api.archive_api._ensure_contract_access", ensure):
            resp = client.post(GENERATE_URL, headers={"x-fachuan-session": single_session})

        # 404 = 已经走到了权限校验（合同不存在），说明守卫放行
        assert resp.status_code == 404
        ensure.assert_awaited_once()

    def test_lawyer_without_header_passes_the_guard(self, client: DjangoTestClient, multi_session: str) -> None:
        """律师手动操作没有会话头；别的会话正在多栏并答也不拦他。"""
        ensure = _access_check()
        with patch("apps.contracts.api.archive_api._ensure_contract_access", ensure):
            resp = client.post(GENERATE_URL)

        assert resp.status_code == 404
        ensure.assert_awaited_once()


class TestSyncCaseMaterials:
    def test_multi_lane_agent_is_refused(self, client: DjangoTestClient, multi_session: str) -> None:
        ensure = _access_check()
        with patch("apps.contracts.api.archive_api._ensure_contract_access", ensure):
            resp = client.post(SYNC_URL, headers={"x-fachuan-session": multi_session})

        assert resp.status_code == 409, resp.content
        body = resp.json()
        assert body["code"] == MULTI_LANE_WRITE_CODE
        assert body["errors"]["endpoint"] == "contracts.archive.sync_case_materials"
        ensure.assert_not_awaited()

    def test_single_lane_agent_passes_the_guard(self, client: DjangoTestClient, single_session: str) -> None:
        ensure = _access_check()
        with patch("apps.contracts.api.archive_api._ensure_contract_access", ensure):
            resp = client.post(SYNC_URL, headers={"x-fachuan-session": single_session})

        assert resp.status_code == 404
        ensure.assert_awaited_once()
