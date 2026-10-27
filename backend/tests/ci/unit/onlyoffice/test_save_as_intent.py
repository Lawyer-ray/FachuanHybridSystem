"""另存为：DS 保存回调落盘时把编辑产物写成新文件，原文件不动。

**为什么整条链路放在一起测**：另存为的正确性不在任何单个函数里，而在
「前端登记的一次性意图」能否活到 DS 回调那一刻、以及消费它之后会不会
被误清。三个失败点各自都能让律师丢掉原稿：

1. 意图没登记成功（会话查不到）→ 保存静默变成原地覆盖；
2. 意图被上一步（stale 判定 / 下载失败）顺手清了 → DS 重试就降级成覆盖；
3. 另存失败却先清了意图 → 同上。

因此本文件一律走**生产路径**：`register_save_as_intent` 登记 →
`load_session_by_key()` 取会话（DS 回调就是这么拿的）→ `handle_save_callback`
落盘；文件系统用 `_Service`（绑定临时目录、无 ACL）打桩，只替换
「哪个目录」，不替换行为。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth import get_user_model

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.onlyoffice.models import EditorSession
from apps.onlyoffice.services import callback_service
from apps.onlyoffice.services.callback_service import (
    find_session_for_source,
    get_or_refresh_session,
    load_session_by_key,
    register_save_as_intent,
    session_id_for_path,
)
from apps.onlyoffice.services.domain_registry import get_domain

CONTRACT_ID = 318
SOURCE_SUBPATH = "1-合同/a.docx"
# 与前端 folderFileUrl 口径一致：subpath 里只有一个字符，编码后仍是它自己
SOURCE_PATH = f"/api/v1/contracts/{CONTRACT_ID}/folder-file?subpath={SOURCE_SUBPATH}"
SAVE_AS_NAME = "a[修订版]V1_20261027.docx"


class _Service(BoundFolderBrowseService):
    """最小可用的具体实现：绑定到临时目录、无 ACL（权限口径另有 API 层用例）。"""

    root: Path

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _require_access(self, **_kw: Any) -> None:
        return None

    def _local_root(self, _owner_id: int) -> Path:
        return self.root


@pytest.fixture
def folder_root(tmp_path: Path) -> Path:
    """绑定根里放一份原稿「1-合同/a.docx」，内容 old。"""
    src_dir = tmp_path / "1-合同"
    src_dir.mkdir(parents=True)
    (src_dir / "a.docx").write_bytes(b"old")
    return tmp_path


@pytest.fixture
def wired(monkeypatch: Any, folder_root: Path) -> Path:
    """把合同文件夹域的服务换成绑定到临时目录的实现。"""
    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(folder_root))
    return folder_root


@pytest.fixture
def user(db: Any) -> Any:
    return get_user_model().objects.create_user(username="lawyer-save-as", password="x")


def _open_editor(user: Any) -> str:
    """走真实签发路径打开文档，返回 document key（DS 回调带的就是它）。"""
    _, key = get_or_refresh_session(
        task_id=session_id_for_path(SOURCE_PATH),
        user=user,
        source_path=SOURCE_PATH,
        version="v1",
        task_type="contract_folder",
    )
    return key


def _run_callback(monkeypatch: Any, key: str, data: bytes = b"edited") -> bool:
    """跑一遍 DS 保存回调（下载那一步打桩，其余全走生产代码）。"""
    monkeypatch.setattr(callback_service, "_download_edited_docx", lambda _url: data)
    session = load_session_by_key(key)
    assert session is not None
    return callback_service.handle_save_callback(session, "http://ds/cache/edited", status=6)


class TestSaveAsThroughCallback:
    @pytest.mark.django_db
    def test_intent_makes_callback_save_new_file(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """核心：登记意图后，回调把内容写进新文件，**原稿一个字节都不变**。"""
        key = _open_editor(user)
        register_save_as_intent(task_type="contract_folder", user=user, source_path=SOURCE_PATH, name=SAVE_AS_NAME)

        assert _run_callback(monkeypatch, key, b"edited") is True

        assert (wired / SOURCE_SUBPATH).read_bytes() == b"old", "另存为绝不能动原文件"
        assert (wired / "1-合同" / SAVE_AS_NAME).read_bytes() == b"edited"

    @pytest.mark.django_db
    def test_intent_consumed_once(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """一次性语义：第一次保存另存，第二次回到原地覆盖。"""
        key = _open_editor(user)
        register_save_as_intent(task_type="contract_folder", user=user, source_path=SOURCE_PATH, name=SAVE_AS_NAME)

        assert _run_callback(monkeypatch, key, b"first") is True
        # 消费后必须已清空（并已持久化：handle_save_callback 末尾整体 save）。
        # 注意 key 已在保存后轮换，老 key 解不到会话，只能按 task 取（与用户自己的
        # 会话唯一），再拿库里那个 key 跑第二次回调。
        session = EditorSession.objects.get(task_type="contract_folder", task_id=session_id_for_path(SOURCE_PATH))
        assert session.pending_save_as_name == ""

        key2 = session.document_key
        assert key2 != key, "保存后必须轮换 document key（否则 DS 继续用缓存旧内容）"
        assert _run_callback(monkeypatch, key2, b"second") is True

        assert (wired / SOURCE_SUBPATH).read_bytes() == b"second"
        # 没有第二次另存产生的新文件
        names = {p.name for p in (wired / "1-合同").iterdir()}
        assert names == {"a.docx", SAVE_AS_NAME}

    @pytest.mark.django_db
    def test_without_intent_overwrites_in_place(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """对照组：没登记意图时保持老行为（原地覆盖），防止另存逻辑把默认路径改坏。"""
        key = _open_editor(user)

        assert _run_callback(monkeypatch, key, b"edited") is True

        assert (wired / SOURCE_SUBPATH).read_bytes() == b"edited"
        names = {p.name for p in (wired / "1-合同").iterdir()}
        assert names == {"a.docx"}

    @pytest.mark.django_db
    def test_failed_save_as_keeps_intent_for_ds_retry(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """另存失败时意图必须保留：DS 重试那一次仍要另存，不能降级成覆盖原稿。"""
        key = _open_editor(user)
        register_save_as_intent(task_type="contract_folder", user=user, source_path=SOURCE_PATH, name=SAVE_AS_NAME)

        from apps.contracts.services.contract.integrations import folder_browse_service as mod

        real = _Service(wired)

        def boom(**_kw: Any) -> dict[str, Any]:
            raise OSError("磁盘满了")

        monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _BoomService(wired, boom))
        assert _run_callback(monkeypatch, key, b"edited") is False

        # 原稿没被动、意图仍在（从库里读，确认不是只活在内存里）
        assert (wired / SOURCE_SUBPATH).read_bytes() == b"old"
        session = EditorSession.objects.get(task_type="contract_folder", task_id=session_id_for_path(SOURCE_PATH))
        assert session.pending_save_as_name == SAVE_AS_NAME

        # DS 重试：这次恢复正常，必须是另存而不是覆盖
        monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(wired))
        assert _run_callback(monkeypatch, key, b"edited") is True
        assert (wired / SOURCE_SUBPATH).read_bytes() == b"old"
        assert (wired / "1-合同" / SAVE_AS_NAME).read_bytes() == b"edited"
        assert real is not None

    @pytest.mark.django_db
    def test_stale_canvas_keeps_intent(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """stale 分支不落盘、也不清意图：用户重开后再保存仍要另存。"""
        key = _open_editor(user)
        register_save_as_intent(task_type="contract_folder", user=user, source_path=SOURCE_PATH, name=SAVE_AS_NAME)
        # AI 划词直改抬了外写代次 → 这份画布过期
        callback_service.bump_external_write(SOURCE_PATH, task_type="contract_folder")

        assert _run_callback(monkeypatch, key, b"stale-canvas") is True

        assert (wired / SOURCE_SUBPATH).read_bytes() == b"old"
        assert not (wired / "1-合同" / SAVE_AS_NAME).exists()
        session = EditorSession.objects.get(task_type="contract_folder", task_id=session_id_for_path(SOURCE_PATH))
        assert session.pending_save_as_name == SAVE_AS_NAME

    @pytest.mark.django_db
    def test_same_name_existing_file_is_not_overwritten(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """新名已存在时加序号（与上传同一套去重），保住上一次的另存产物。"""
        (wired / "1-合同" / SAVE_AS_NAME).write_bytes(b"previous")
        key = _open_editor(user)
        register_save_as_intent(task_type="contract_folder", user=user, source_path=SOURCE_PATH, name=SAVE_AS_NAME)

        assert _run_callback(monkeypatch, key, b"edited") is True

        assert (wired / "1-合同" / SAVE_AS_NAME).read_bytes() == b"previous"
        assert (wired / "1-合同" / "a[修订版]V1_20261027_1.docx").read_bytes() == b"edited"


class _BoomService(_Service):
    """save_new_file 必炸的服务（模拟磁盘满 / 权限错这类真失败）。"""

    def __init__(self, root: Path, boom: Any) -> None:
        super().__init__(root)
        self._boom = boom

    def save_new_file(self, **_kw: Any) -> dict[str, Any]:
        return self._boom(**_kw)


class TestIntentRegistration:
    @pytest.mark.django_db
    def test_finds_session_by_source_path(self, user: Any) -> None:
        _open_editor(user)
        session = find_session_for_source(task_type="contract_folder", user=user, source_path=SOURCE_PATH)
        assert session is not None
        assert session.task_type == "contract_folder"

    @pytest.mark.django_db
    def test_missing_session_raises_clear_error(self, user: Any) -> None:
        """用户还没打开编辑器：必须明确报错让前端提示「请先打开文档」。"""
        with pytest.raises(NotFoundError) as exc:
            register_save_as_intent(task_type="contract_folder", user=user, source_path=SOURCE_PATH, name=SAVE_AS_NAME)
        assert "打开" in str(exc.value.message)

    @pytest.mark.django_db
    def test_other_users_source_does_not_match(self, user: Any) -> None:
        """别人的会话不能被这条意图命中（两人同开时意图天然隔离）。"""
        other = get_user_model().objects.create_user(username="another-lawyer", password="x")
        _open_editor(other)
        assert find_session_for_source(task_type="contract_folder", user=user, source_path=SOURCE_PATH) is None

    @pytest.mark.django_db
    def test_other_domain_does_not_match(self, user: Any) -> None:
        """同名路径在别的业务域（case_folder）不算命中。"""
        _open_editor(user)
        alt = SOURCE_PATH.replace("/contracts/", "/cases/")
        assert find_session_for_source(task_type="case_folder", user=user, source_path=alt) is None


class TestAdoptEditedDirect:
    """钩子本身的边界（不经回调），补 callback 层覆盖不到的分支。"""

    @pytest.mark.django_db
    def test_returns_new_subpath_in_saved_name(self, wired: Path, user: Any) -> None:
        """另存时返回的是新文件标识（用于日志定位写到哪儿了）。"""
        domain = get_domain("contract_folder")
        assert domain is not None
        _open_editor(user)
        register_save_as_intent(task_type="contract_folder", user=user, source_path=SOURCE_PATH, name=SAVE_AS_NAME)
        session = EditorSession.objects.get(task_type="contract_folder", task_id=session_id_for_path(SOURCE_PATH))

        assert domain.adopt_edited(session, b"edited", 1) == f"{CONTRACT_ID}:1-合同/{SAVE_AS_NAME}"

    @pytest.mark.django_db
    def test_unparseable_source_path_keeps_intent(self, wired: Path, user: Any) -> None:
        """源路径解不出契约：报错让 DS 重试，意图不能顺手清掉。"""
        domain = get_domain("contract_folder")
        assert domain is not None

        class _S:
            task_type = "contract_folder"
            source_path = "/api/v1/contracts/abc/unknown"
            user = None
            pending_save_as_name = SAVE_AS_NAME

        with pytest.raises(RuntimeError):
            domain.adopt_edited(_S(), b"x", 1)
        assert _S.pending_save_as_name == SAVE_AS_NAME


class TestNameSanitizing:
    """意图里的名字最终会成为磁盘路径部件，必须在登记前就清洗。"""

    def test_traversal_and_separators_rejected(self) -> None:
        svc = _Service(Path("/tmp"))
        for bad in ("../../etc/passwd", "a/b.docx", "..\\..\\x.docx", ".hidden.docx", ""):
            with pytest.raises(ValidationException):
                svc._validator.sanitize_file_name(svc._clean_entry_name(bad))

    def test_valid_name_passes(self) -> None:
        svc = _Service(Path("/tmp"))
        assert svc._validator.sanitize_file_name(svc._clean_entry_name(SAVE_AS_NAME)) == SAVE_AS_NAME
