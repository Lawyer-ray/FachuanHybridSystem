"""OnlyOffice 端点集成测试（真实 DB + Django test client）。

覆盖我新增的三个端点：
- GET /onlyoffice/editor-config：配置签发（含签名 token、下载地址、模式权限）
- GET /onlyoffice/file：DS 取文件代理（签名鉴权、路径白名单、越权拒绝）
- POST /onlyoffice/callback：DS 状态回调（协议应答、token 解析容错）

为什么要这一层（而不是只测纯函数）：三个端点串起来才构成「DS 能拿到文件并回写」，
单独测 sign/verify 无法暴露「路径白名单漏了」「权限判定用了错的 user」这类问题。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.test import Client

from apps.contract_review.models.review_task import ReviewTask
from apps.core.models.system_config import SystemConfig
from apps.onlyoffice.services.signing import (
    document_type_of,
    file_type_of,
    make_document_key,
    sign_file_token,
    verify_file_token,
)

pytestmark = pytest.mark.django_db

SECRET = "test-onlyoffice-secret-long-enough-for-hs256"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _clear_config_cache() -> Any:
    """配置读取带 TTL 缓存：每个用例前后清空，防止跨用例串值。"""
    from apps.onlyoffice.config import clear_config_cache

    clear_config_cache()
    yield
    clear_config_cache()


@pytest.fixture
def cfg_ready() -> Any:
    """把三项配置写进 SystemConfig（enabled=True）。"""
    for key, value in (
        ("ONLYOFFICE_DOCSERVER_URL", "http://ds.local"),
        ("ONLYOFFICE_INTERNAL_URL", "http://backend.local"),
        ("ONLYOFFICE_JWT_SECRET", SECRET),
    ):
        SystemConfig.objects.update_or_create(
            key=key,
            defaults={"value": value, "category": "onlyoffice", "is_active": True},
        )
    yield


@pytest.fixture
def api_client(user: Any) -> Client:
    """带 JWT 的 test client。"""
    from ninja_jwt.tokens import RefreshToken

    c = Client()
    token = str(RefreshToken.for_user(user).access_token)
    c.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return c


@pytest.fixture
def user(db: Any) -> Any:
    """ReviewTask.user 指向 AUTH_USER_MODEL（organization.Lawyer）。"""
    from apps.testing.factories import LawyerFactory

    return LawyerFactory(username="oo_tester")


@pytest.fixture
def task_with_result(user: Any, settings: Any) -> Any:
    """造一个已完成的审查任务 + 真实产物文件（放在 MEDIA_ROOT 下，走真实解析路径）。"""
    import uuid
    from pathlib import Path

    rel = f"contract_review/test/{uuid.uuid4().hex}.docx"
    abs_path = Path(settings.MEDIA_ROOT) / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(b"PK\x03\x04fake-docx")

    # 原件也要存在（download-original 用）
    rel_orig = f"contract_review/test/{uuid.uuid4().hex}.docx"
    abs_orig = Path(settings.MEDIA_ROOT) / rel_orig
    abs_orig.write_bytes(b"PK\x03\x04original")

    return ReviewTask.objects.create(
        user=user,
        original_file=rel_orig,
        output_file=rel,
        status="completed",
    )


class TestEditorConfigEndpoint:
    """GET /onlyoffice/editor-config"""

    def test_returns_disabled_when_not_configured(self, api_client: Client) -> None:
        """三项配置缺失时 enabled=False，并给出可读原因（前端据此显示「未启用」）。"""
        SystemConfig.objects.filter(key__startswith="ONLYOFFICE_").update(value="")
        r = api_client.get(
            "/api/v1/onlyoffice/editor-config",
            {"file_url": "/api/v1/contract-review/x/download", "file_name": "a.docx"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert "未配置" in body["reason"]

    def test_signs_config_and_proxies_file_via_signed_url(self, api_client: Client, cfg_ready: Any) -> None:
        """启用后：返回签名 token + DS 可达的 /onlyoffice/file 代理地址。"""
        r = api_client.get(
            "/api/v1/onlyoffice/editor-config",
            {
                "file_url": "/api/v1/contract-review/abc/download",
                "file_name": "合同.docx",
                "mode": "review",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert body["docserver_url"] == "http://ds.local"

        cfg = body["config"]
        assert cfg["documentType"] == "word"
        assert cfg["token"], "config 必须带签名 token（DS 开 JWT 时整份 config 都要签）"

        # 文件地址走代理端点，不是原来的 /contract-review/.../download
        url = cfg["document"]["url"]
        assert url.startswith("http://backend.local/api/v1/onlyoffice/file?")
        assert "src=" in url and "sig=" in url
        # 原路径被 URL 编码进 src
        assert "contract-review%2Fabc%2Fdownload" in url

    def test_review_mode_keeps_canvas_but_locks_body(self, api_client: Client, cfg_ready: Any) -> None:
        """锁定修订：mode=edit（否则 DS 不建画布），靠 permissions.edit=false 禁止改正文。"""
        r = api_client.get(
            "/api/v1/onlyoffice/editor-config",
            {"file_url": "/api/v1/x/download", "file_name": "a.docx", "mode": "review"},
        )
        cfg = r.json()["config"]
        assert cfg["editorConfig"]["mode"] == "edit"
        assert cfg["document"]["permissions"]["edit"] is False
        assert cfg["document"]["permissions"]["review"] is True

    def test_edit_mode_allows_body_edit(self, api_client: Client, cfg_ready: Any) -> None:
        r = api_client.get(
            "/api/v1/onlyoffice/editor-config",
            {"file_url": "/api/v1/x/download", "file_name": "a.docx", "mode": "edit"},
        )
        cfg = r.json()["config"]
        assert cfg["document"]["permissions"]["edit"] is True

    def test_version_change_rotates_cache_key(self, api_client: Client, cfg_ready: Any) -> None:
        """DS 按 key 缓存：文件版本变了 key 必须变，否则看到旧内容。"""
        p = {"file_url": "/api/v1/x/download", "file_name": "a.docx"}
        k1 = api_client.get("/api/v1/onlyoffice/editor-config", {**p, "version": "v1"}).json()["config"]["document"][
            "key"
        ]
        k2 = api_client.get("/api/v1/onlyoffice/editor-config", {**p, "version": "v2"}).json()["config"]["document"][
            "key"
        ]
        assert k1 != k2

    def test_rejects_unsupported_format(self, api_client: Client, cfg_ready: Any) -> None:
        """未知后缀不再伪装 word（word 编辑器打不开 xlsm 之类），明确提示不支持。"""
        r = api_client.get(
            "/api/v1/onlyoffice/editor-config",
            {"file_url": "/api/v1/x/download", "file_name": "a.zip"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert "不支持" in body["reason"]

    def test_requires_auth(self, cfg_ready: Any) -> None:
        r = Client().get(
            "/api/v1/onlyoffice/editor-config",
            {"file_url": "/api/v1/x/download", "file_name": "a.docx"},
        )
        assert r.status_code == 401
        # 未鉴权不能拿到签名配置：响应里不该出现 DS 的 JWT 或回调地址
        body = r.content.decode("utf-8", "ignore")
        assert "callbackUrl" not in body
        assert "docserver_url" not in body

    def test_long_encoded_folder_file_url_survives_session_upsert(
        self, api_client: Client, cfg_ready: Any, user: Any
    ) -> None:
        """回归（2026-10-27 真机 500）：长中文文件名的 folder-file 路径必须能建会话。

        contract_folder 域把整条 URL 存进 EditorSession.source_path；subpath 是
        URL 编码后的中文案由名（1 汉字 ≈ 9 ASCII），案由级文件名轻松超 500。
        放宽前 session.save() 抛 StringDataRightTruncation → editor-config 500 →
        前端「文档打开失败」。
        """
        from urllib.parse import quote

        from apps.onlyoffice.models import EditorSession

        # 虚构当事人：只借「案由级长文件名」的形态，不带真实案件信息
        real_name = (
            "1-民商事合同（甲公司诉乙公司、丙公司、丁公司及第三人戊公司"
            "建设工程施工合同纠纷执行异议之诉一案测试用超长文件名）V2_20261020.docx"
        )
        file_url = f"/api/v1/contracts/386/folder-file?subpath={quote(real_name)}"
        assert len(file_url) > 500, "回归前提：编码后路径必须真的超旧上限"

        r = api_client.get(
            "/api/v1/onlyoffice/editor-config",
            {"file_url": file_url, "file_name": real_name, "mode": "view"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True, body.get("reason")

        # 会话已建且存的是全量路径（保存回写靠它反解 subpath）
        session = EditorSession.objects.filter(task_type="contract_folder", source_path=file_url, user=user).first()
        assert session is not None
        assert len(session.document_key) == 32


class TestFileProxyEndpoint:
    """GET /onlyoffice/file —— DS 取文件代理"""

    def test_serves_file_with_valid_signature(self, cfg_ready: Any, task_with_result: Any, user: Any) -> None:
        src = f"/api/v1/contract-review/{task_with_result.id}/download"
        sig = sign_file_token(SECRET, src, str(user.pk))
        r = Client().get("/api/v1/onlyoffice/file", {"src": src, "sig": sig})
        assert r.status_code == 200
        # FileResponse 是流式的：必须消费掉 content 才有内容
        body = b"".join(r.streaming_content) if r.streaming else r.content
        assert body == b"PK\x03\x04fake-docx"

    def test_percent_encoded_query_survives_single_decode(
        self, cfg_ready: Any, task_with_result: Any, user: Any
    ) -> None:
        """回归：含百分号编码查询串的 src 只允许被解码一次。

        Django 解析查询串时已对 src unquote 过一次（wire 上的 %25E5... → %E5...），
        端点拿到的应正是签名时的原始字符串；若服务端再 unquote 一次（%E5%90%88%E5%90%8C
        → 合同），验签对象错位、HMAC 不匹配，该请求会 403（修复前正是如此）。
        签名必须对原始字符串做，而不是对编码形态做。
        """
        src = f"/api/v1/contract-review/{task_with_result.id}/download?fn=%E5%90%88%E5%90%8C.docx"
        sig = sign_file_token(SECRET, src, str(user.pk))
        r = Client().get("/api/v1/onlyoffice/file", {"src": src, "sig": sig})
        assert r.status_code == 200
        body = b"".join(r.streaming_content) if r.streaming else r.content
        assert body == b"PK\x03\x04fake-docx"

    def test_rejects_bad_signature(self, cfg_ready: Any, task_with_result: Any) -> None:
        src = f"/api/v1/contract-review/{task_with_result.id}/download"
        r = Client().get("/api/v1/onlyoffice/file", {"src": src, "sig": "1.9999999999.deadbeef"})
        assert r.status_code == 403
        assert r.content[:2] != b"PK"

    def test_rejects_expired_token(self, cfg_ready: Any, task_with_result: Any, user: Any) -> None:
        src = f"/api/v1/contract-review/{task_with_result.id}/download"
        sig = sign_file_token(SECRET, src, str(user.pk), ttl_seconds=-1)
        r = Client().get("/api/v1/onlyoffice/file", {"src": src, "sig": sig})
        assert r.status_code == 403
        assert r.content[:2] != b"PK"

    def test_rejects_external_url(self, cfg_ready: Any) -> None:
        """开放代理防护：只允许站内 /api/ 路径。"""
        src = "http://evil.example.com/secret"
        sig = sign_file_token(SECRET, src, "1")
        r = Client().get("/api/v1/onlyoffice/file", {"src": src, "sig": sig})
        assert r.status_code == 403
        # 拒绝必须真的不吐文件：状态码对但正文带文档内容等于没拦住
        assert r.content[:2] != b"PK"

    def test_rejects_scheme_in_path(self, cfg_ready: Any) -> None:
        """路径校验通过、验签也通过，但 uid 指向的用户不存在 → 403。

        推导链：src 以 /api/ 开头且不含 ://，路径校验放行；sig 是本测试自签的
        合法签名，验签通过并解出 uid="1"；测试库里 pk=1 的 Lawyer 不存在
        （user fixture 在其他用例的事务里创建，回滚后不残留）→ 必然 403，
        不可能是 404（拒绝发生在用户校验层，不在路由解析层）。
        """
        src = "/api/v1/../../etc/passwd"
        sig = sign_file_token(SECRET, src, "1")
        r = Client().get("/api/v1/onlyoffice/file", {"src": src, "sig": sig})
        assert r.status_code == 403
        # 越权必须真的不吐文件
        assert r.content[:2] != b"PK"

    def test_other_users_task_is_forbidden(self, cfg_ready: Any, task_with_result: Any) -> None:
        """签名合法但用户无权访问该任务 → 不返回文件。"""
        from apps.testing.factories import LawyerFactory

        other = LawyerFactory(username="other")
        src = f"/api/v1/contract-review/{task_with_result.id}/download"
        sig = sign_file_token(SECRET, src, str(other.pk))
        r = Client().get("/api/v1/onlyoffice/file", {"src": src, "sig": sig})
        assert r.status_code == 404
        # 越权与不存在同样回 404，且都不能吐出文件字节
        assert r.content[:2] != b"PK", "越权用户拿到了别人的合同"


class TestCallbackEndpoint:
    """POST /onlyoffice/callback"""

    def test_acks_plain_body(self, cfg_ready: Any) -> None:
        """DS 要求返回 {"error": 0}，否则会反复重试。"""
        r = Client().post(
            "/api/v1/onlyoffice/callback",
            data=json.dumps({"key": "k1", "status": 1}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.json() == {"error": 0}

    def test_acks_signed_body(self, cfg_ready: Any) -> None:
        """带合法 JWT token 的回调正常应答（token 解析失败不应 500）。"""
        import jwt

        payload = {"key": "k2", "status": 1}
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        r = Client().post(
            "/api/v1/onlyoffice/callback",
            data=json.dumps({"token": token}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.json() == {"error": 0}

    def test_rejects_bad_token(self, cfg_ready: Any) -> None:
        """token 存在但验不过 → 拒绝处理（error:1），不回落未签名 body。"""
        r = Client().post(
            "/api/v1/onlyoffice/callback",
            data=json.dumps({"token": "not-a-jwt", "key": "k", "status": 1}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.json() == {"error": 1}

    def test_tolerates_malformed_body(self, cfg_ready: Any) -> None:
        """坏 JSON 不能把回调打挂（DS 会一直重试）。"""
        r = Client().post("/api/v1/onlyoffice/callback", data="not-json", content_type="application/json")
        assert r.status_code == 200
        assert r.json() == {"error": 0}

    def test_is_public(self, cfg_ready: Any) -> None:
        """DS 调用无用户身份，该端点必须免鉴权。"""
        r = Client().post(
            "/api/v1/onlyoffice/callback",
            data=json.dumps({"key": "k3", "status": 4}),
            content_type="application/json",
        )
        assert r.status_code == 200
        # 免鉴权只意味着「能进」，仍须按协议回 {error: 0}——否则 DS 会重试
        assert r.json() == {"error": 0}


class TestSaveCallback:
    """status=2/6 保存回写：下载 DS 给的 url → 落回任务产物 → 轮换 key。"""

    @pytest.fixture
    def session_ctx(self, api_client: Client, cfg_ready: Any, task_with_result: Any, user: Any) -> Any:
        """走真实链路建会话：editor-config 签发时自动 upsert EditorSession。"""
        src = f"/api/v1/contract-review/{task_with_result.id}/download"
        r = api_client.get(
            "/api/v1/onlyoffice/editor-config",
            {"file_url": src, "file_name": "合同.docx", "version": "v9"},
        )
        assert r.status_code == 200
        key = r.json()["config"]["document"]["key"]
        return {"task": task_with_result, "user": user, "src": src, "key": key}

    def _post_callback(self, payload: dict[str, Any]) -> Any:
        import jwt as _jwt

        token = _jwt.encode(payload, SECRET, algorithm="HS256")
        return Client().post(
            "/api/v1/onlyoffice/callback",
            data=json.dumps({"token": token}),
            content_type="application/json",
        )

    def test_save_persists_edited_doc_and_rotates_key(self, session_ctx: Any, monkeypatch: Any, settings: Any) -> None:
        """status=6：下载编辑产物 → 替换任务产物（旧文件留档）→ key 轮换。"""
        from pathlib import Path

        from apps.onlyoffice.models import EditorSession

        task = session_ctx["task"]
        old_output = task.output_file
        old_abs = Path(settings.MEDIA_ROOT) / old_output

        def _fake_get(url: str, **kwargs: Any) -> Any:
            assert url == "http://ds.local/cache/edited.docx"
            assert kwargs.get("trust_env") is False, "内网 DS 地址必须绕过系统代理"

            class _Resp:
                content = b"PK\x03\x04edited-by-lawyer"
                raise_for_status = lambda self: None  # noqa: E731

            return _Resp()

        monkeypatch.setattr("apps.onlyoffice.services.callback_service.httpx.get", _fake_get)

        r = self._post_callback(
            {
                "key": session_ctx["key"],
                "status": 6,
                "url": "http://ds.local/cache/edited.docx",
            }
        )
        assert r.status_code == 200
        assert r.json() == {"error": 0}

        task.refresh_from_db()
        assert task.output_file != old_output
        assert "律编v1" in task.output_file
        # 旧产物物理文件保留（留档可恢复）
        assert old_abs.exists()
        # 新产物可读
        new_abs = Path(settings.MEDIA_ROOT) / task.output_file
        assert new_abs.read_bytes() == b"PK\x03\x04edited-by-lawyer"
        # key 轮换：saved_version+1 后算出新 key，下次打开 DS 取新内容
        session = EditorSession.objects.get(task_id=task.id, user=session_ctx["user"])
        assert session.saved_version == 1
        assert session.document_key != session_ctx["key"]
        assert session.prev_output_file == old_output

    def test_save_failure_returns_error_1_for_ds_retry(self, session_ctx: Any, monkeypatch: Any) -> None:
        """下载失败 → error:1（DS 会重试），任务产物不动。"""

        def _boom(url: str, **kwargs: Any) -> Any:
            raise RuntimeError("ds unavailable")

        monkeypatch.setattr("apps.onlyoffice.services.callback_service.httpx.get", _boom)
        r = self._post_callback({"key": session_ctx["key"], "status": 2, "url": "http://ds.local/x.docx"})
        assert r.json() == {"error": 1}
        task = session_ctx["task"]
        task.refresh_from_db()
        assert "律编" not in (task.output_file or "")

    def test_save_rejects_unsigned_body(self, session_ctx: Any) -> None:
        """status=2 无签名 → 拒绝落盘（伪造回调不能注入任意 url 覆盖文件）。"""
        r = Client().post(
            "/api/v1/onlyoffice/callback",
            data=json.dumps({"key": session_ctx["key"], "status": 2, "url": "http://evil/x.docx"}),
            content_type="application/json",
        )
        assert r.json() == {"error": 1}
        task = session_ctx["task"]
        task.refresh_from_db()
        assert "律编" not in (task.output_file or "")

    def test_save_rejects_unknown_key(self, cfg_ready: Any) -> None:
        """key 查不到会话 → error:1（不静默吞掉，让 DS 停止重试无效文档）。"""
        r = self._post_callback({"key": "nonexistent-key-000000000000", "status": 6, "url": "http://ds/x"})
        assert r.json() == {"error": 1}

    def test_same_doc_same_key_across_users(self, session_ctx: Any, api_client: Client, user: Any) -> None:
        """两名律师同开同一份合同 → 同一 document key（DS 实时协同的前提）。"""
        from apps.testing.factories import LawyerFactory

        other = LawyerFactory(username="oo_collaborator")
        from ninja_jwt.tokens import RefreshToken

        c2 = Client()
        c2.defaults["HTTP_AUTHORIZATION"] = f"Bearer {RefreshToken.for_user(other).access_token}"
        r = c2.get(
            "/api/v1/onlyoffice/editor-config",
            {
                "file_url": session_ctx["src"],
                "file_name": "合同.docx",
                "version": "v9",
            },
        )
        assert r.status_code == 200
        assert r.json()["config"]["document"]["key"] == session_ctx["key"]


class TestSigningHelpers:
    """签名工具的边界（纯函数，但错了整条链就断）"""

    def test_document_type_mapping(self) -> None:
        assert document_type_of("a.docx") == "word"
        assert document_type_of("a.xlsx") == "cell"
        assert document_type_of("a.pptx") == "slide"
        assert document_type_of("a.pdf") == "pdf"
        # 未知后缀返回 ""：表示不支持预览，前端显示「该格式暂不支持在线预览」
        assert document_type_of("a.unknown") == ""
        assert document_type_of("a.zip") == ""
        assert document_type_of("a.exe") == ""

    def test_file_type_of(self) -> None:
        assert file_type_of("合同.DOCX") == "docx"
        # 无后缀同样视为不支持，返回 ""
        assert file_type_of("无后缀") == ""

    def test_document_key_is_stable_and_versioned(self) -> None:
        a = make_document_key("/x/download", "v1")
        b = make_document_key("/x/download", "v1")
        c = make_document_key("/x/download", "v2")
        d = make_document_key("/x/download", "v1", 1)
        assert a == b, "同文件同版本必须复用 key（否则每次重开都重新转换）"
        assert a != c
        assert a != d, "保存回写后 saved_version+1 必须换 key（否则 DS 用缓存旧内容）"

    def test_token_roundtrip(self) -> None:
        src = "/api/v1/x/download"
        sig = sign_file_token(SECRET, src, "42")
        assert verify_file_token(SECRET, src, sig) == "42"

    def test_token_binds_to_path(self) -> None:
        """换路径后签名不再有效（防止拿 A 文件的签名取 B 文件）。"""
        sig = sign_file_token(SECRET, "/api/v1/a/download", "42")
        assert verify_file_token(SECRET, "/api/v1/b/download", sig) is None

    def test_token_binds_to_secret(self) -> None:
        sig = sign_file_token(SECRET, "/api/v1/a", "42")
        assert verify_file_token("another-secret", "/api/v1/a", sig) is None

    def test_malformed_token_returns_none(self) -> None:
        assert verify_file_token(SECRET, "/api/v1/a", "junk") is None
        assert verify_file_token(SECRET, "/api/v1/a", "") is None
