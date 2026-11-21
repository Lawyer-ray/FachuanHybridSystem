"""写端点的多栏兜底（入口 C）：`/direct-edit/apply` 与 `/patch/apply`。

## 为什么在 HTTP 层测

写降级的前两道闸门都以**工具名**为判据（pi 的 `--exclude-tools`、审批层的
`MULTI_LANE_WRITE_TOOLS`）。工具名漏登记、或调用绕过 MCP 工具面时，只有 REST
端点按**会话**兜底拦得住。四条口径缺一不可：

1. 带会话头 + 该会话多栏登记 → 409，且文件字节一个都没变；
2. 带会话头 + 单栏 → 200（回归：别把单栏也拒了）；
3. 不带会话头（律师在页面上点）→ 200（回归：别一刀切打穿律师自己的按钮）；
4. patch 应用由律师点出（无会话头），但 patch 行属于多栏会话 → 409。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from django.test import Client as DjangoTestClient
from docx import Document

from apps.agent.services.approval.policy import clear_multi_lane_session, mark_multi_lane_session
from apps.agent.services.approval.write_guard import MULTI_LANE_WRITE_CODE
from apps.contract_review.services.formatting.docx_revision_tool import visible_text
from apps.contract_review.services.patch.models import ContractWritePatch, PatchStatus
from tests.ci.unit.contract_review.services.patch.docx_fixtures import CLAUSE_PAYMENT, SUBPATH

APPLY_URL = "/api/v1/contract-review/direct-edit/apply"
PROPOSE_URL = "/api/v1/contract-review/direct-edit/patch/propose"
PATCH_APPLY_URL = "/api/v1/contract-review/direct-edit/patch/apply"
SUGGESTED = "甲方应于十五日内支付货款。"
MULTI = "direct-edit-multi-lane"
SINGLE = "direct-edit-single-lane"


@pytest.fixture
def client() -> DjangoTestClient:
    return DjangoTestClient()


@pytest.fixture
def multi_session() -> Any:
    mark_multi_lane_session(MULTI)
    try:
        yield MULTI
    finally:
        clear_multi_lane_session(MULTI)


@pytest.fixture
def single_session() -> Any:
    """登记后立刻收尾（计数归零＝单栏），走的是真实收尾路径而不是「从没登记」。"""
    mark_multi_lane_session(SINGLE)
    clear_multi_lane_session(SINGLE)
    return SINGLE


def _apply(client: DjangoTestClient, contract_id: int, *, session_id: str | None) -> Any:
    headers = {"x-fachuan-session": session_id} if session_id else {}
    return client.post(
        APPLY_URL,
        data={"contract_id": contract_id, "subpath": SUBPATH, "selection": CLAUSE_PAYMENT, "suggested": SUGGESTED},
        content_type="application/json",
        headers=headers,
    )


class TestApplyEdit:
    @pytest.mark.django_db(transaction=True)
    def test_agent_on_multi_lane_session_is_refused_without_touching_the_file(
        self, client: DjangoTestClient, bound: Any, multi_session: str
    ) -> None:
        lawyer, contract, file_path = bound()
        client.force_login(lawyer)
        before = file_path.read_bytes()

        resp = _apply(client, contract.id, session_id=multi_session)

        assert resp.status_code == 409, resp.content
        body = resp.json()
        assert body["code"] == MULTI_LANE_WRITE_CODE
        # 文案要可自纠：告诉模型改用 propose_write_patch，而不是只说「不行」
        assert "propose_write_patch" in body["message"]
        assert body["errors"]["endpoint"] == "contract_review.direct_edit.apply"
        assert body["errors"]["session_id"] == multi_session
        # 拒写在落盘之前：文件字节一个都没变
        assert file_path.read_bytes() == before

    @pytest.mark.django_db(transaction=True)
    def test_agent_on_single_lane_session_still_writes(
        self, client: DjangoTestClient, bound: Any, single_session: str
    ) -> None:
        lawyer, contract, file_path = bound()
        client.force_login(lawyer)

        resp = _apply(client, contract.id, session_id=single_session)

        assert resp.status_code == 200, resp.content
        assert resp.json()["applied"] is True
        # 落盘后能读到修订插入的文本（visible_text 口径：含 w:ins、不含 w:del）
        doc = Document(BytesIO(Path(file_path).read_bytes()))
        assert SUGGESTED in visible_text(doc.paragraphs[0])

    @pytest.mark.django_db(transaction=True)
    def test_lawyer_without_session_header_is_never_blocked(
        self, client: DjangoTestClient, bound: Any, multi_session: str
    ) -> None:
        """页面上的「采纳」不带会话头：别的会话正在多栏并答也不影响律师本人操作。"""
        lawyer, contract, _file_path = bound()
        client.force_login(lawyer)

        resp = _apply(client, contract.id, session_id=None)

        assert resp.status_code == 200, resp.content
        assert resp.json()["applied"] is True


class TestApplyWritePatches:
    @pytest.mark.django_db(transaction=True)
    def test_patch_from_multi_lane_session_is_refused_even_without_header(
        self, client: DjangoTestClient, bound: Any, multi_session: str
    ) -> None:
        lawyer, contract, file_path = bound()
        client.force_login(lawyer)
        before = file_path.read_bytes()
        # 提案自带产出会话（MCP 从 X-Fachuan-Session 取），提案本身不写盘、必须放行
        proposed = client.post(
            PROPOSE_URL,
            data={
                "contract_id": contract.id,
                "subpath": SUBPATH,
                "original": CLAUSE_PAYMENT,
                "replacement": SUGGESTED,
                "session_id": multi_session,
            },
            content_type="application/json",
        )
        assert proposed.status_code == 200, proposed.content
        patch_id = proposed.json()["patch_id"]

        # 应用请求由律师在页面点出（无会话头），只能靠 patch 行兜底
        resp = client.post(PATCH_APPLY_URL, data={"patch_ids": [patch_id]}, content_type="application/json")

        assert resp.status_code == 409, resp.content
        body = resp.json()
        assert body["code"] == MULTI_LANE_WRITE_CODE
        assert body["errors"]["endpoint"] == "contract_review.direct_edit.patch_apply"
        assert body["errors"]["session_id"] == multi_session
        # 一个字都没写，草案仍在「待裁决」状态（律师收尾后可再应用）
        assert file_path.read_bytes() == before
        assert ContractWritePatch.objects.get(patch_id=patch_id).status == PatchStatus.PROPOSED
