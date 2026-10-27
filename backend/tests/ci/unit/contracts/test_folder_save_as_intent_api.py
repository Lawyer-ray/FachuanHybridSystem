"""`folder-save-as-intent` 端点：只登记意图、不写文件，权限口径与 folder-save 一致。

**为什么要独立测端点**：这条链路的字节要等 DS 回调才落盘（见
`tests/ci/unit/onlyoffice/test_save_as_intent.py`），所以端点本身能守住的
只有三件事，而每一件出问题都会让「另存为」变成「改坏原稿」：

1. **ACL 不能比 folder-save 宽**——否则越权用户能改别人文档的落盘目标；
2. **文件名必须在这里就清洗**——名字会进会话、最终成为磁盘路径部件，
   放到回调时才失败，用户看不到任何错误；
3. **找不到会话要明确报错**——静默成功会让前端提示「已另存」，
   而真正保存时走的是原地覆盖。

HTTP 层用 Django 的同步测试客户端（会话认证），不打桩 auth 以外的东西。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from django.test import Client as DjangoTestClient

from apps.contracts.models import ContractAssignment, ContractFolderBinding
from apps.onlyoffice.models import EditorSession
from apps.onlyoffice.services.callback_service import get_or_refresh_session, session_id_for_path
from apps.testing.factories import ContractFactory, LawyerFactory

SUBPATH = "1-合同/a.docx"
SOURCE_PATH = f"/api/v1/contracts/{{cid}}/folder-file?subpath={quote(SUBPATH, safe='')}"
NEW_NAME = "a[修订版]V1_20261027.docx"


def _url(contract_id: int) -> str:
    return f"/api/v1/contracts/{contract_id}/folder-save-as-intent"


@pytest.fixture
def client() -> DjangoTestClient:
    return DjangoTestClient()


@pytest.fixture
def bound(tmp_path: Path) -> Any:
    """一份已绑定临时目录、带原稿的合同 + 被指派的律师（有 ACL 访问权）。"""

    def _make() -> tuple[Any, Any, Path]:
        src_dir = tmp_path / "1-合同"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "a.docx").write_bytes(b"old")
        lawyer = LawyerFactory()
        contract = ContractFactory()
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer)
        ContractFolderBinding.objects.create(contract=contract, folder_path=str(tmp_path))
        return lawyer, contract, tmp_path

    return _make


def _session_of(contract_id: int) -> EditorSession:
    return EditorSession.objects.get(
        task_type="contract_folder", task_id=session_id_for_path(SOURCE_PATH.format(cid=contract_id))
    )


def _open_editor(lawyer: Any, contract_id: int) -> str:
    """按前端 folderFileUrl 口径签发一次会话（端点靠 source_path 逐字匹配找它）。"""
    source_path = SOURCE_PATH.format(cid=contract_id)
    _, key = get_or_refresh_session(
        task_id=session_id_for_path(source_path),
        user=lawyer,
        source_path=source_path,
        version="v1",
        task_type="contract_folder",
    )
    return key


class TestSaveAsIntentEndpoint:
    @pytest.mark.django_db(transaction=True)
    def test_registers_intent_without_writing_file(self, client: DjangoTestClient, bound: Any) -> None:
        lawyer, contract, root = bound()
        client.force_login(lawyer)
        _open_editor(lawyer, contract.id)

        resp = client.post(
            _url(contract.id), data={"subpath": SUBPATH, "name": NEW_NAME}, content_type="application/json"
        )

        assert resp.status_code == 200, resp.content
        assert resp.json()["name"] == NEW_NAME
        # 只登记、不写文件：目录里仍然只有原稿
        assert {p.name for p in (root / "1-合同").iterdir()} == {"a.docx"}
        session = _session_of(contract.id)
        assert session.pending_save_as_name == NEW_NAME

    @pytest.mark.django_db(transaction=True)
    def test_name_with_path_traversal_rejected(self, client: DjangoTestClient, bound: Any) -> None:
        """`../../etc/passwd` 这种名字必须 400，绝不能被登记进会话。"""
        lawyer, contract, _root = bound()
        client.force_login(lawyer)
        _open_editor(lawyer, contract.id)

        resp = client.post(
            _url(contract.id), data={"subpath": SUBPATH, "name": "../../etc/passwd"}, content_type="application/json"
        )

        assert resp.status_code == 400, resp.content
        assert _session_of(contract.id).pending_save_as_name == ""

    @pytest.mark.django_db(transaction=True)
    def test_no_active_session_reports_clear_error(self, client: DjangoTestClient, bound: Any) -> None:
        """用户还没在 OnlyOffice 里打开过文档：明确 404 + 提示「请先打开」。"""
        lawyer, contract, _root = bound()
        client.force_login(lawyer)

        resp = client.post(
            _url(contract.id), data={"subpath": SUBPATH, "name": NEW_NAME}, content_type="application/json"
        )

        assert resp.status_code == 404, resp.content
        assert "打开" in resp.content.decode("utf-8")

    @pytest.mark.django_db(transaction=True)
    def test_unauthorized_user_denied(self, client: DjangoTestClient, bound: Any) -> None:
        """ACL 与 folder-save 同口径：非指派律师一律拒（不能改别人文档的落盘目标）。"""
        _owner, contract, _root = bound()
        outsider = LawyerFactory()
        client.force_login(outsider)
        _open_editor(outsider, contract.id)  # 即使他有会话，也不能越过合同 ACL

        resp = client.post(
            _url(contract.id), data={"subpath": SUBPATH, "name": NEW_NAME}, content_type="application/json"
        )

        assert resp.status_code in (403, 404), resp.content
        assert _session_of(contract.id).pending_save_as_name == ""

    @pytest.mark.django_db(transaction=True)
    def test_missing_source_file_rejected(self, client: DjangoTestClient, bound: Any) -> None:
        """源文件不存在 → 404（与 folder-save 同一套 resolve_file 判定），不登记。"""
        lawyer, contract, _root = bound()
        client.force_login(lawyer)
        _open_editor(lawyer, contract.id)

        resp = client.post(
            _url(contract.id), data={"subpath": "1-合同/nope.docx", "name": NEW_NAME}, content_type="application/json"
        )

        assert resp.status_code == 404, resp.content


class TestEndpointIsRegistered:
    def test_route_registered_on_contracts_router(self) -> None:
        """路由必须真的挂在合同 browse router 上，且挂在 /contracts 前缀下。

        名字对不上前端就接不上（返回 404，前端只能报「未知错误」）。
        """
        from apiSystem.api import api_v1
        from apps.contracts.api.contract_folder_browse_api import router as folder_router

        paths = list(folder_router.path_operations.keys())
        assert "/{contract_id}/folder-save-as-intent" in paths, f"缺少另存意图路由；现有: {paths}"

        prefixes = [prefix for prefix, _router in api_v1._routers]
        assert "/contracts" in prefixes, f"合同 router 未挂载到 /contracts；现有前缀: {prefixes}"
