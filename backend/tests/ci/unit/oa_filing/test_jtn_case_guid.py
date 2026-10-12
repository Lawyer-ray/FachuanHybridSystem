"""JtnCaseGuidScript（案号查 GUID，列表页搜索 + 飞连一键登录自愈）单测（无网络）。

覆盖：VIEWSTATE 提取、GUID 提取（行解析 + 正则兜底）、完整查询编排
（命中/多命中/0 命中/SSO 门户一键恢复/本地客户端不可用/兑换失败/登录失败/
网关死拦/会话中途失效重试）、三字段（案号/案名/客户名）的 postback 字段、
ScriptExecutorService 三个查询入口的装配与错误映射。
HTTP 全部走 httpx.MockTransport 或实例打桩；本机飞连客户端 token 打桩。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from apps.oa_filing.services.oa_scripts.jtn.case_guid.constants import (
    _SEARCH_CASE_NAME_FIELD,
    _SEARCH_CASE_NO_FIELD,
    _SEARCH_CUST_NAME_FIELD,
)
from apps.oa_filing.services.oa_scripts.jtn.case_guid.service import (
    JtnCaseGuidScript,
    extract_case_guids,
    extract_viewstate_fields,
)
from apps.oa_filing.services.oa_scripts.jtn.http_session import is_oa_login_page

_GUID_A = "b0219b56-3968-48a8-8e12-3ca86bf160ce"
_GUID_B = "0f2b7a11-1111-2222-3333-444455556666"

_CASE_NO = "2026TEST0001"
_CASE_LIST_URL = "https://ims.jtn.com/project/index.aspx?FirstModel=PROJECT&SecondModel=PROJECT002"
_SSO_AUTHORIZE_URL = "https://access.jtn.com/api/oidc/authorize?client_id=fSDxmmzBdYmrJYzK"
_SSO_PORTAL_LOGIN_URL = "https://access.jtn.com/login?next=%2Fapi%2Foidc%2Fauthorize"
_GATEWAY_CALLBACK_URL = "https://ims.jtn.com/corplink/agw/callback?code=diag-1"
_APP_LOGIN_URL = "https://ims.jtn.com/member/login.aspx?rurl=https%3a%2f%2fims.jtn.com%2fproject"

_LOCAL_TOKEN_STUB_PATH = "apps.oa_filing.services.oa_scripts.jtn.case_guid.service._fetch_local_quick_login_token"


def _list_page_html() -> str:
    return (
        "<html><body><form id='aspnetForm'>"
        f'<input type="hidden" id="__VIEWSTATE" value="VS-{_CASE_NO}" />'
        '<input type="hidden" id="__VIEWSTATEGENERATOR" value="134513E2" />'
        "</form></body></html>"
    )


def _result_page_html(*guids: str, case_no: str = _CASE_NO) -> str:
    rows = "".join(
        f"<tr><td>{case_no} 案件</td>"
        f"<td><a href='../project/projectView.aspx?keyid={g}&FirstModel=PROJECT'>查看</a></td></tr>"
        for g in guids
    )
    return f"<html><body><table>{rows}</table></body></html>"


def _login_page_html() -> str:
    return "<html><body>location.replace('https://ims.jtn.com/member/login.aspx?rurl=x')</body></html>"


def _app_login_page_html() -> str:
    """OA 应用层登录页（含 CSRFToken 与账密表单）。"""
    return (
        "<html><body><form>"
        '<input type="hidden" name="CSRFToken" value="csrf-1" />'
        '<input name="userid"><input name="password">'
        "</form></body></html>"
    )


def _make_script(handler: Any, *, http_login: Any = None, cached_cookies: Any = None) -> tuple[JtnCaseGuidScript, Any]:
    """构造脚本实例：http_login/load_cookies 打桩 + MockTransport 客户端，返回 (script, http_login mock)。"""
    script = JtnCaseGuidScript(account="acc", password="p")
    transport = httpx.MockTransport(handler)
    if http_login is None:
        http_login = AsyncMock(return_value={"ASP.NET_SessionId": "s1"})
    auth: Any = MagicMock()
    auth.http_login = http_login
    auth.load_cookies = MagicMock(return_value=cached_cookies)
    script._auth = auth

    def _build_client(*, cookies: dict[str, str]) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": "test"},
            follow_redirects=True,
            timeout=5,
            cookies=cookies,
            trust_env=False,
            transport=transport,
        )

    script._build_client = _build_client  # type: ignore[assignment, method-assign]
    return script, http_login


# ──────────── VIEWSTATE 提取 ────────────


class TestExtractViewstateFields:
    def test_present(self):
        fields = extract_viewstate_fields(_list_page_html())
        assert fields == {"__VIEWSTATE": f"VS-{_CASE_NO}", "__VIEWSTATEGENERATOR": "134513E2"}

    def test_absent(self):
        assert extract_viewstate_fields("<html><body>登录页</body></html>") == {}


# ──────────── 登录页判定 ────────────


class TestIsOaLoginPage:
    def test_login_url(self):
        assert is_oa_login_page("https://ims.jtn.com/member/login.aspx?rurl=x", "任意内容") is True

    def test_location_replace_placeholder(self):
        assert is_oa_login_page(_CASE_LIST_URL, _login_page_html()) is True

    def test_normal_page(self):
        assert is_oa_login_page(_CASE_LIST_URL, _list_page_html()) is False

    def test_marker_in_long_page_is_not_login(self):
        long_page = "x" * 3000 + "location.replace(...)"
        assert is_oa_login_page(_CASE_LIST_URL, long_page) is False


# ──────────── GUID 提取 ────────────


class TestExtractCaseGuids:
    def test_row_parse_single(self):
        html = _result_page_html(_GUID_A)
        assert extract_case_guids(html, _CASE_NO) == [_GUID_A]

    def test_row_parse_multi_keeps_order_and_dedupes(self):
        html = _result_page_html(_GUID_B, _GUID_A, _GUID_B)
        assert extract_case_guids(html, _CASE_NO) == [_GUID_B, _GUID_A]

    def test_no_rows_found_returns_empty(self):
        # lxml 可解析但无命中行：视为真 0 命中，不整页捞回（防误提页面其他区域的 keyid）
        html = f"<div>杂乱文本</div><a href='/p?keyid={_GUID_A}&x=1'>链接</a>"
        assert extract_case_guids(html, _CASE_NO) == []

    def test_unparseable_html_falls_back_to_regex(self):
        # lxml 解析失败（非法 HTML 触发异常的构造）→ 回退文档同款整页正则
        broken = f"<a href='/p?keyid={_GUID_A}&x=1'>链接"
        with patch(
            "apps.oa_filing.services.oa_scripts.jtn.case_guid.service.lxml_html.fromstring",
            side_effect=ValueError("boom"),
        ):
            assert extract_case_guids(broken, _CASE_NO) == [_GUID_A]

    def test_rows_without_keyword_excluded(self):
        html = _result_page_html(_GUID_A, case_no="2099ZZZ0001")
        assert extract_case_guids(html, _CASE_NO) == []

    def test_no_hit_returns_empty(self):
        assert extract_case_guids(_list_page_html(), _CASE_NO) == []


# ──────────── 查询编排（网关/SSO 门户/应用层三层自愈模拟器） ────────────


class _SelfHealServer:
    """模拟 ims.jtn.com 前置飞连网关 + SSO 门户 + OA 应用层的会话语义。

    会话层级（cookie 驱动）：
    - SSO 门户：`sso=ok`（门户会话）。缺失时 GET 业务页被弹到
      access.jtn.com/login（飞连 SPA 登录页）——需本机客户端一键登录恢复；
    - 网关：`corplink_at`。有 SSO 会话但缺网关 token 时，业务页 302 到
      corplink/agw/callback（Set-Cookie 下发网关会话，body 为 JS 回跳页）；
    - OA 应用层：`ASP.NET_SessionId=ok123`。有网关 token 但缺应用会话时，
      业务页 302 到 member/login.aspx（CSRFToken 账密表单）；
    - quick-login 兑换：POST /api/quick-login 携带 `{"token": "good-token"}` →
      Set-Cookie sso=ok（token 不对/csrf 缺失 → code=194008 当前登录方式未开启）。
    """

    _GOOD_TOKEN = "good-token"

    def __init__(
        self,
        *,
        app_session: str = "ok123",
        login_error: bool = False,
        gateway_dead: bool = False,
        quick_login_reject: bool = False,
        result_guids: tuple[str, ...] = (_GUID_A,),
    ) -> None:
        self.app_session = app_session
        self.login_error = login_error
        self.gateway_dead = gateway_dead
        self.quick_login_reject = quick_login_reject
        self.result_guids = result_guids
        self.search_posts: list[dict[str, list[str]]] = []
        self.quick_login_calls: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        cookie = request.headers.get("cookie", "")
        parsed = urlparse(str(request.url))
        host, path = parsed.netloc, parsed.path

        if "api/quick-login" in path:
            body = request.read()
            import json as _json

            payload = _json.loads(body) if body else {}
            csrf = request.headers.get("csrf-token", "")
            self.quick_login_calls.append({"payload": payload, "csrf": csrf, "os": parse_qs(parsed.query).get("os")})
            if self.quick_login_reject or payload.get("token") != self._GOOD_TOKEN or not csrf:
                return httpx.Response(200, json={"code": 194008, "message": "当前登录方式未开启"})
            return httpx.Response(
                200,
                headers=[("Set-Cookie", "sso=ok; Domain=access.jtn.com; Path=/")],
                json={"code": 0, "data": {"result": "success"}},
            )
        if "api/oidc/authorize" in path:
            # 网关授权端点：门户会话（access.jtn.com 域 cookie）有效则发 code 弹网关
            # 回调，无效则弹门户登录页。sso cookie 只随 access.jtn.com 请求发送。
            if "sso=ok" in cookie:
                return httpx.Response(302, headers=[("Location", _GATEWAY_CALLBACK_URL)])
            return httpx.Response(302, headers=[("Location", _SSO_PORTAL_LOGIN_URL)])
        if host == "access.jtn.com":
            # 门户登录页（SPA）：无 SSO 会话时的落点；authorize 跳转已 Set-Cookie
            # 门户 csrf-token / 匿名 session（兑换一次性 token 需要 csrf 头）
            return httpx.Response(
                200,
                headers=[
                    ("Set-Cookie", "csrf-token=portalc; Domain=access.jtn.com; Path=/"),
                    ("Set-Cookie", "session=anon; Domain=access.jtn.com; Path=/"),
                ],
                text="<html>feilian portal login SPA</html>",
            )
        if "corplink/agw" in path:
            if self.gateway_dead:
                return httpx.Response(200, text="<html>gateway stuck</html>")
            return httpx.Response(
                302,
                headers=[
                    ("Set-Cookie", "corplink_at=fresh; Path=/"),
                    ("Set-Cookie", "corplink_it=fresh2; Path=/"),
                    ("Location", _CASE_LIST_URL),
                ],
            )
        if "member/login.aspx" in path:
            if request.method == "POST":
                if self.login_error:
                    return httpx.Response(200, text='<input name="userid"><input name="password">账号或密码错误')
                return httpx.Response(
                    302,
                    headers=[
                        ("Set-Cookie", f"ASP.NET_SessionId={self.app_session}; Path=/"),
                        ("Location", _CASE_LIST_URL),
                    ],
                )
            return httpx.Response(200, text=_app_login_page_html())

        # 业务页（列表页 / 搜索）——SSO 会话 cookie 只在 access.jtn.com 域，
        # ims.jtn.com 侧的状态只由 corplink_at（网关）与应用层会话驱动
        has_app_session = f"ASP.NET_SessionId={self.app_session}" in cookie
        has_gateway = "corplink_at=" in cookie

        if request.method == "POST":
            posted = {k: v for k, v in parse_qs(request.content.decode()).items() if "projmainPlaceHolder" in k}
            self.search_posts.append(posted)
            if has_app_session:
                # 行文本带上提交的过滤词（行解析按关键词匹配行内文本）
                keyword = next((v[0] for v in posted.values() if v and v[0]), "")
                return httpx.Response(200, text=_result_page_html(*self.result_guids, case_no=keyword or _CASE_NO))
            return httpx.Response(302, headers=[("Location", _APP_LOGIN_URL)])

        if has_app_session:
            return httpx.Response(200, text=_list_page_html())
        if has_gateway:
            return httpx.Response(302, headers=[("Location", _APP_LOGIN_URL)])
        # 无网关 token → 弹网关授权端点（由 authorize 决定发 code 或弹门户登录）
        return httpx.Response(302, headers=[("Location", _SSO_AUTHORIZE_URL)])


def _stub_local_token(token: str | None) -> AsyncMock:
    return AsyncMock(return_value=token)


class TestLookupCaseGuids:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "lookup",
        [
            lambda s: s.lookup_case_guids("   "),
            lambda s: s.lookup_case_guids_by_name("  "),
            lambda s: s.lookup_case_guids_by_customer_name(" "),
        ],
        ids=["case_no", "case_name", "customer_name"],
    )
    async def test_empty_keyword_skips_network(self, lookup):
        server = _SelfHealServer()
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return server.handler(request)

        script, _ = _make_script(handler)
        assert await lookup(script) == []
        assert calls["n"] == 0

    @pytest.mark.asyncio
    async def test_fresh_cached_session_direct_hit(self):
        """缓存会话新鲜：GET 直达列表页，无需自愈与 http_login。"""
        server = _SelfHealServer()
        cached = [{"name": "ASP.NET_SessionId", "value": "ok123", "domain": "ims.jtn.com", "path": "/"}]
        script, http_login = _make_script(server.handler, cached_cookies=cached)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert len(server.search_posts) == 1
        assert server.search_posts[0][_SEARCH_CASE_NO_FIELD] == [_CASE_NO]
        http_login.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sso_expired_recovers_via_local_quick_login(self):
        """SSO 门户会话过期：本机飞连客户端一键登录 → 网关回调 → 应用层登录 → 搜索。

        复现 2026-10-12 线上断供场景（缓存 SSO 会话过期，旧链路每轮弹门户登录页死循环）。
        """
        server = _SelfHealServer()
        cached = [{"name": "ASP.NET_SessionId", "value": "stale", "domain": "ims.jtn.com", "path": "/"}]
        script, _ = _make_script(server.handler, cached_cookies=cached)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        # 兑换请求：os=web 查询参数 + csrf 头 + 一次性 token
        assert len(server.quick_login_calls) == 1
        call = server.quick_login_calls[0]
        assert call["os"] == ["web"]
        assert call["payload"] == {"token": _SelfHealServer._GOOD_TOKEN, "login_scene": "feilian"}
        assert call["csrf"]

    @pytest.mark.asyncio
    async def test_sso_recovery_without_gateway_then_form_login(self):
        """无缓存冷启动：一键恢复 → 网关回调 Set-Cookie → 应用层账密登录 → 搜索。"""
        server = _SelfHealServer()
        script, _ = _make_script(server.handler, cached_cookies=None)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert len(server.search_posts) == 1

    @pytest.mark.asyncio
    async def test_local_client_unavailable_raises_friendly(self):
        """本机飞连客户端不可用：报「客户端不可用」而非笼统会话错误。"""
        server = _SelfHealServer()
        script, _ = _make_script(server.handler)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(None)):
            with pytest.raises(RuntimeError, match="飞连客户端不可用"):
                await script.lookup_case_guids(_CASE_NO)

    @pytest.mark.asyncio
    async def test_quick_login_rejected_raises_friendly(self):
        """门户拒绝兑换（如 os 参数缺失/方式未开启）：报「一键登录恢复失败」。"""
        server = _SelfHealServer(quick_login_reject=True)
        script, _ = _make_script(server.handler)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            with pytest.raises(RuntimeError, match="一键登录恢复失败"):
                await script.lookup_case_guids(_CASE_NO)

    @pytest.mark.asyncio
    async def test_stale_gateway_cookie_does_not_block_self_heal(self):
        """缓存里残留已失效的网关 token：自愈前必须清掉，否则与新下发值共存死循环。"""
        server = _SelfHealServer()
        cached = [
            {"name": "ASP.NET_SessionId", "value": "stale", "domain": "ims.jtn.com", "path": "/"},
            {"name": "corplink_at", "value": "stale", "domain": ".ims.jtn.com", "path": "/"},
            {"name": "corplink_it", "value": "stale", "domain": ".ims.jtn.com", "path": "/"},
        ]
        script, _ = _make_script(server.handler, cached_cookies=cached)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]

    @pytest.mark.asyncio
    async def test_multi_hit(self):
        server = _SelfHealServer(result_guids=(_GUID_B, _GUID_A, _GUID_B))
        script, _ = _make_script(server.handler)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            assert await script.lookup_case_guids(_CASE_NO) == [_GUID_B, _GUID_A]

    @pytest.mark.asyncio
    async def test_no_hit_returns_empty_list(self):
        server = _SelfHealServer(result_guids=())
        script, _ = _make_script(server.handler)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            assert await script.lookup_case_guids(_CASE_NO) == []

    @pytest.mark.asyncio
    async def test_login_failure_raises_account_error(self):
        server = _SelfHealServer(login_error=True)
        script, _ = _make_script(server.handler)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            with pytest.raises(RuntimeError, match="账号或密码错误"):
                await script.lookup_case_guids(_CASE_NO)

    @pytest.mark.asyncio
    async def test_gateway_dead_loop_raises(self):
        """网关死拦（回调不下发会话）→ 明确报「会话无法建立」。"""
        server = _SelfHealServer(gateway_dead=True)
        script, _ = _make_script(server.handler)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            with pytest.raises(RuntimeError, match="会话无法建立"):
                await script.lookup_case_guids(_CASE_NO)

    @pytest.mark.asyncio
    async def test_session_expired_mid_search_retries_once(self):
        """搜索时会话突然失效：整体重试一次后成功。"""
        server = _SelfHealServer()
        original = server.handler
        state = {"expired_once": False}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and "project/index.aspx" in str(request.url):
                if not state["expired_once"]:
                    state["expired_once"] = True
                    return httpx.Response(302, headers=[("Location", _APP_LOGIN_URL)])
            return original(request)

        script, _ = _make_script(handler)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert state["expired_once"] is True  # 首次搜索触发过会话失效
        assert len(server.search_posts) == 1  # 重试后的成功搜索

    @pytest.mark.asyncio
    async def test_plain_page_without_viewstate_raises(self):
        """无任何登录/网关特征但拿不到 VIEWSTATE → 会话无法建立。"""
        script, _ = _make_script(lambda request: httpx.Response(200, text="<html><body>异常页</body></html>"))
        with pytest.raises(RuntimeError, match="会话无法建立"):
            await script.lookup_case_guids(_CASE_NO)


class TestLookupByOtherFields:
    """案名 / 客户名入口：同一列表页 postback，仅过滤字段不同。"""

    @pytest.mark.asyncio
    async def test_by_name_posts_project_name_field(self):
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            server = _SelfHealServer()
            script, _ = _make_script(server.handler)
            assert await script.lookup_case_guids_by_name("某公司 合同纠纷") == [_GUID_A]
            assert server.search_posts[-1][_SEARCH_CASE_NAME_FIELD] == ["某公司 合同纠纷"]

    @pytest.mark.asyncio
    async def test_by_customer_name_posts_cust_field(self):
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            server = _SelfHealServer()
            script, _ = _make_script(server.handler)
            assert await script.lookup_case_guids_by_customer_name("腾讯") == [_GUID_A]
            assert server.search_posts[-1][_SEARCH_CUST_NAME_FIELD] == ["腾讯"]

    @pytest.mark.asyncio
    async def test_by_name_self_heals_too(self):
        """案名入口同样走完整自愈链（SSO 过期场景）。"""
        server = _SelfHealServer()
        cached = [{"name": "ASP.NET_SessionId", "value": "stale", "domain": "ims.jtn.com", "path": "/"}]
        script, _ = _make_script(server.handler, cached_cookies=cached)
        with patch(_LOCAL_TOKEN_STUB_PATH, _stub_local_token(_SelfHealServer._GOOD_TOKEN)):
            assert await script.lookup_case_guids_by_name("某案名") == [_GUID_A]


# ──────────── 调度器装配 ────────────


class TestLookupOaCaseGuidExecutor:
    def _make_user(self) -> MagicMock:
        return MagicMock(id=1)

    def _make_adapter(self, method_name: str, result: list[str] | Exception) -> tuple[MagicMock, dict[str, Any]]:
        adapter = MagicMock()
        captured: dict[str, Any] = {}

        async def fake_lookup(keyword: str, credential: Any) -> list[str]:
            captured["keyword"] = keyword
            captured["credential"] = credential
            if isinstance(result, Exception):
                raise result
            return result

        setattr(adapter, method_name, fake_lookup)
        return adapter, captured

    def _run(self, method_name: str, keyword: str, adapter: MagicMock, credential: MagicMock):
        import asyncio

        from apps.oa_filing.services import script_executor_service as mod

        with (
            patch.object(mod, "_find_credential", return_value=credential),
            patch.object(mod, "create_adapter", return_value=adapter) as mock_create,
            patch.object(mod, "run_coro_sync", side_effect=lambda coro, **kw: asyncio.run(coro)),
        ):
            result = getattr(mod.ScriptExecutorService(), method_name)(keyword, user=self._make_user())
        assert mock_create.call_args[0] == ("金诚同达OA", "acc", "p")
        return result

    def test_missing_credential_raises(self):
        from apps.oa_filing.services import script_executor_service as mod

        service = mod.ScriptExecutorService()
        with patch.object(mod, "_find_credential", return_value=None):
            with pytest.raises(RuntimeError, match="未找到匹配凭证"):
                service.lookup_oa_case_guid(case_no=_CASE_NO, user=self._make_user())

    def test_success_returns_guids(self):
        adapter, captured = self._make_adapter("lookup_case_guid", [_GUID_A])
        result = self._run("lookup_oa_case_guid", f"  {_CASE_NO}  ", adapter, MagicMock(account="acc", password="p"))
        assert result == [_GUID_A]
        assert captured["keyword"] == _CASE_NO  # strip 生效

    @pytest.mark.parametrize(
        ("executor_method", "adapter_method"),
        [
            ("lookup_oa_case_guid_by_name", "lookup_case_guid_by_name"),
            ("lookup_oa_case_guid_by_customer_name", "lookup_case_guid_by_customer_name"),
        ],
    )
    def test_name_and_customer_entries_delegate_with_strip(self, executor_method, adapter_method):
        adapter, captured = self._make_adapter(adapter_method, [_GUID_B])
        credential = MagicMock(account="acc", password="p")
        result = self._run(executor_method, "  某公司  ", adapter, credential)
        assert result == [_GUID_B]
        assert captured["keyword"] == "某公司"
        assert captured["credential"] is credential

    def test_error_mapped_to_friendly_message(self):
        adapter, _ = self._make_adapter("lookup_case_guid", RuntimeError("Read timed out"))
        with pytest.raises(RuntimeError, match="VPN"):
            self._run("lookup_oa_case_guid", _CASE_NO, adapter, MagicMock(account="acc", password="p"))

    @pytest.mark.django_db
    def test_query_uses_requesting_users_own_credential(self):
        """谁登录就用谁的 JTN 账号发起查询：两位律师各配各的凭证，请求者 A 不得用到 B 的。"""
        import asyncio

        from apps.oa_filing.services import script_executor_service as mod
        from apps.organization.models import AccountCredential, Lawyer

        lawyer_a = Lawyer.objects.create_user(username="guid_user_a", real_name="甲律师")
        lawyer_b = Lawyer.objects.create_user(username="guid_user_b", real_name="乙律师")
        AccountCredential.objects.create(
            lawyer=lawyer_a,
            site_name="金诚同达OA",
            account="acct_a",
            password="pa-not-secret",  # pragma: allowlist secret
        )
        AccountCredential.objects.create(
            lawyer=lawyer_b,
            site_name="金诚同达OA",
            account="acct_b",
            password="pb-not-secret",  # pragma: allowlist secret
        )

        captured: dict[str, Any] = {}

        class _FakeAdapter:
            async def lookup_case_guid(self, case_no: str, credential: Any) -> list[str]:
                captured["credential_account"] = str(credential.account)
                return []

        def fake_create_adapter(site_name: str, account: str, password: str) -> _FakeAdapter:
            captured["adapter_account"] = account
            return _FakeAdapter()

        with (
            patch.object(mod, "create_adapter", side_effect=fake_create_adapter),
            patch.object(mod, "run_coro_sync", side_effect=lambda coro, **kw: asyncio.run(coro)),
        ):
            mod.ScriptExecutorService().lookup_oa_case_guid(case_no=_CASE_NO, user=lawyer_a)

        assert captured["adapter_account"] == "acct_a"
        assert captured["credential_account"] == "acct_a"
