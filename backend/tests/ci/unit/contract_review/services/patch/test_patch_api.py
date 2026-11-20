"""`/direct-edit/patch/propose|apply` 两个端点的形状与守卫。

MCP 侧的两个工具只是这两个端点的薄转发，所以这里的断言就是"模型能不能正确
提案 / 应用"的证据：

- `propose` 回执必须带 `patch_id` 与 `base_mtime`（乐观锁的锚），且**不改文件**；
- `apply` 走服务层的同一套守卫：互斥冲突 409、且一个字都不写。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.test import Client as DjangoTestClient

from apps.contract_review.services.patch.models import ContractWritePatch, PatchStatus
from tests.ci.unit.contract_review.services.patch.docx_fixtures import CLAUSE_COURT, CLAUSE_PAYMENT, SUBPATH

PROPOSE_URL = "/api/v1/contract-review/direct-edit/patch/propose"
APPLY_URL = "/api/v1/contract-review/direct-edit/patch/apply"
PAYMENT_A = "甲方应于十五日内支付货款。"
PAYMENT_B = "甲方应于十日内支付货款。"


@pytest.fixture
def client() -> DjangoTestClient:
    return DjangoTestClient()


def _propose(client: DjangoTestClient, contract_id: int, original: str, replacement: str) -> Any:
    return client.post(
        PROPOSE_URL,
        data={
            "contract_id": contract_id,
            "subpath": SUBPATH,
            "original": original,
            "replacement": replacement,
            "session_id": "s-api",
            "turn": 3,
        },
        content_type="application/json",
    )


class TestProposeEndpoint:
    @pytest.mark.django_db(transaction=True)
    def test_propose_returns_patch_id_and_base_mtime_without_writing(
        self, client: DjangoTestClient, bound: Any
    ) -> None:
        lawyer, contract, file_path = bound()
        client.force_login(lawyer)
        before = file_path.read_bytes()

        resp = _propose(client, contract.id, CLAUSE_PAYMENT, PAYMENT_A)

        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["status"] == PatchStatus.PROPOSED
        assert body["patch_id"] and body["subpath"] == SUBPATH
        # base_mtime 是提案时刻的磁盘值（应用前要拿它做二次校验）
        assert body["base_mtime"] == pytest.approx(file_path.stat().st_mtime, abs=1.0)
        assert body["session_id"] == "s-api" and body["turn"] == 3
        assert file_path.read_bytes() == before

    @pytest.mark.django_db(transaction=True)
    def test_propose_requires_exactly_one_owner_id(self, client: DjangoTestClient, bound: Any) -> None:
        lawyer, _contract, _path = bound()
        client.force_login(lawyer)
        resp = client.post(
            PROPOSE_URL,
            data={"subpath": SUBPATH, "original": CLAUSE_PAYMENT, "replacement": PAYMENT_A},
            content_type="application/json",
        )
        assert resp.status_code == 400, resp.content
        # 断言到「为什么 400」：只断状态码时，把校验理由改成任何东西都是绿的
        # （`test_test_quality_ratchet` 也禁止纯状态码断言）
        body = resp.json()
        assert "二选一" in str(body), body


class TestApplyEndpoint:
    @pytest.mark.django_db(transaction=True)
    def test_apply_complementary_patches(self, client: DjangoTestClient, bound: Any) -> None:
        lawyer, contract, file_path = bound()
        client.force_login(lawyer)
        first = _propose(client, contract.id, CLAUSE_PAYMENT, PAYMENT_A).json()["patch_id"]
        second = _propose(client, contract.id, CLAUSE_COURT, "由甲方所在地法院管辖。").json()["patch_id"]

        resp = client.post(
            APPLY_URL,
            data={"patch_ids": [first, second], "note": "两处都采纳"},
            content_type="application/json",
        )

        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert sorted(body["applied"]) == sorted([first, second])
        assert body["subpath"] == SUBPATH
        assert ContractWritePatch.objects.filter(patch_id__in=[first, second], status=PatchStatus.APPLIED).count() == 2
        assert file_path.exists()

    @pytest.mark.django_db(transaction=True)
    def test_apply_overlap_returns_409_and_keeps_file(self, client: DjangoTestClient, bound: Any) -> None:
        lawyer, contract, file_path = bound()
        client.force_login(lawyer)
        before = file_path.read_bytes()
        first = _propose(client, contract.id, CLAUSE_PAYMENT, PAYMENT_A).json()["patch_id"]
        second = _propose(client, contract.id, CLAUSE_PAYMENT, PAYMENT_B).json()["patch_id"]

        resp = client.post(APPLY_URL, data={"patch_ids": [first, second]}, content_type="application/json")

        assert resp.status_code == 409, resp.content
        assert resp.json()["code"] == "PATCH_OVERLAP"
        assert len(resp.json()["errors"]["conflicts"]) == 1
        assert file_path.read_bytes() == before
