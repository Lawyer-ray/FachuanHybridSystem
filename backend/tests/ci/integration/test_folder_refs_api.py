"""folder-refs API 集成测试：真实 HTTP 走三个端点（创建引用 / 读内容 / 页图）。

权限口径与 folder-entries 同（行级 ACL）——ACL 判定本身由 contracts 侧覆盖，
这里 monkeypatch 放行，专注端点契约：回执字段、4xx 规整、引用型不落
media、删除会话不触碰绑定原文件。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from apps.agent.models import AgentAttachment, AgentSession
from apps.contracts.models import Contract, ContractFolderBinding
from apps.organization.models import LawFirm, Lawyer


@pytest.fixture()
def setup(
    db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Lawyer, Client, Contract, Path, AgentSession]:
    from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

    monkeypatch.setattr(ContractFolderBrowseService, "_require_access", lambda self, **kw: None)
    firm = LawFirm.objects.create(name="folder-ref-api-律所")
    user = Lawyer.objects.create_user(
        username="folderref-api", password="x-test-12345678", law_firm=firm  # pragma: allowlist secret
    )  # pragma: allowlist secret
    client = Client()
    client.force_login(user)
    root = tmp_path / "bound"
    (root / "0-律师资料").mkdir(parents=True)
    (root / "0-律师资料" / "委托合同.txt").write_text("委托代理合同正文", encoding="utf-8")
    contract = Contract.objects.create(name="folder-ref-api-合同", case_type="civil")
    ContractFolderBinding.objects.create(contract=contract, folder_path=str(root))
    session = AgentSession.objects.create(user=user, origin=AgentSession.Origin.CONTRACT, contract_id=contract.id)
    return user, client, contract, root, session


def _post_ref(client: Client, session: AgentSession, contract_id: int, subpath: str) -> tuple[int, dict[str, Any]]:
    resp = client.post(
        f"/api/v1/agent/sessions/{session.session_id}/folder-refs",
        data=json.dumps({"kind": "contract", "owner_id": contract_id, "subpath": subpath}),
        content_type="application/json",
    )
    return resp.status_code, resp.json()


class TestCreateFolderRefApi:
    def test_success_returns_ref_receipt(self, setup: tuple[Lawyer, Client, Contract, Path, AgentSession]) -> None:
        _, client, contract, _, session = setup
        status, body = _post_ref(client, session, contract.id, "0-律师资料/委托合同.txt")
        assert status == 200
        assert body["filename"] == "委托合同.txt"
        assert body["ref_contract_id"] == contract.id
        assert body["ref_subpath"] == "0-律师资料/委托合同.txt"
        # 引用型不复制字节：storage_path 留空
        record = AgentAttachment.objects.get(attachment_id=body["attachment_id"])
        assert record.storage_path == ""

    def test_missing_file_is_404(self, setup: tuple[Lawyer, Client, Contract, Path, AgentSession]) -> None:
        _, client, contract, _, session = setup
        status, _ = _post_ref(client, session, contract.id, "0-律师资料/不存在.txt")
        assert status == 404

    def test_escape_subpath_is_400(self, setup: tuple[Lawyer, Client, Contract, Path, AgentSession]) -> None:
        _, client, contract, _, session = setup
        status, _ = _post_ref(client, session, contract.id, "../../etc/passwd")
        assert status == 400

    def test_delete_session_keeps_source_file(self, setup: tuple[Lawyer, Client, Contract, Path, AgentSession]) -> None:
        _, client, contract, root, session = setup
        status, body = _post_ref(client, session, contract.id, "0-律师资料/委托合同.txt")
        assert status == 200
        source = root / "0-律师资料" / "委托合同.txt"
        session.delete()
        assert AgentAttachment.objects.filter(attachment_id=body["attachment_id"]).count() == 0
        assert source.exists()
        assert source.read_text(encoding="utf-8") == "委托代理合同正文"


class TestContentAndPagesApi:
    def test_content_returns_base64(self, setup: tuple[Lawyer, Client, Contract, Path, AgentSession]) -> None:
        _, client, contract, _, _ = setup
        import base64 as b64

        resp = client.get(
            "/api/v1/agent/folder-refs/content",
            {"kind": "contract", "owner_id": contract.id, "subpath": "0-律师资料/委托合同.txt"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert b64.b64decode(body["content_base64"]).decode("utf-8") == "委托代理合同正文"
        assert body["attachment_id"].startswith(f"folder:{contract.id}/")

    def test_content_requires_auth(self, setup: tuple[Lawyer, Client, Contract, Path, AgentSession]) -> None:
        # 未登录客户端直接访问（不用 fixture 的 client，避免会话污染）
        anon = Client()
        resp = anon.get(
            "/api/v1/agent/folder-refs/content",
            {"kind": "contract", "owner_id": 1, "subpath": "x.txt"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"] == "Unauthorized"
        assert "content_base64" not in body

    def test_pages_unsupported_mime_returns_200_with_error(
        self, setup: tuple[Lawyer, Client, Contract, Path, AgentSession]
    ) -> None:
        """txt 没有页图形态：200 + error=unsupported_mime，不用空图冒充成功。"""
        _, client, contract, _, _ = setup
        resp = client.get(
            "/api/v1/agent/folder-refs/pages",
            {"kind": "contract", "owner_id": contract.id, "subpath": "0-律师资料/委托合同.txt", "pages": "1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] == "unsupported_mime"
        assert body["pages_returned"] == []

    def test_pages_rejects_bad_pages_spec(self, setup: tuple[Lawyer, Client, Contract, Path, AgentSession]) -> None:
        _, client, contract, _, _ = setup
        resp = client.get(
            "/api/v1/agent/folder-refs/pages",
            {"kind": "contract", "owner_id": contract.id, "subpath": "0-律师资料/委托合同.txt", "pages": "abc"},
        )
        assert resp.status_code == 400
        body = resp.json()
        # 错误体指明 pages 字段不合法（人话 message 带字段名与示例格式）
        assert "pages" in body["message"]
        assert "abc" in body["message"]

    def test_pages_missing_file_is_404_with_reason(
        self, setup: tuple[Lawyer, Client, Contract, Path, AgentSession]
    ) -> None:
        _, client, contract, _, _ = setup
        resp = client.get(
            "/api/v1/agent/folder-refs/pages",
            {"kind": "contract", "owner_id": contract.id, "subpath": "0-律师资料/没了.pdf", "pages": "1"},
        )
        assert resp.status_code == 404
        assert "不存在" in resp.json()["message"]
