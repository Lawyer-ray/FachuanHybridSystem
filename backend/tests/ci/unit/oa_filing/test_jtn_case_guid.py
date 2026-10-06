"""JtnCaseGuidScript（案号查 GUID，方法一）可测单元单测（无网络）。

覆盖：VIEWSTATE 提取、登录页判定、GUID 提取（行解析 + 正则兜底）、
完整查询编排（命中/多命中/0 命中/会话失效重试/登录失败）、
ScriptExecutorService.lookup_oa_case_guid 装配与错误映射。
HTTP 全部走 httpx.MockTransport 或实例打桩。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

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

    script._build_client = _build_client  # type: ignore[method-assign]
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
        assert is_oa_login_page("https://ims.jtn.com/project/index.aspx", _login_page_html()) is True

    def test_normal_page(self):
        assert is_oa_login_page("https://ims.jtn.com/project/index.aspx", _list_page_html()) is False

    def test_marker_in_long_page_is_not_login(self):
        long_page = "x" * 3000 + "location.replace(...)"
        assert is_oa_login_page("https://ims.jtn.com/project/index.aspx", long_page) is False


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

    def test_rows_without_case_no_excluded(self):
        html = _result_page_html(_GUID_A, case_no="2099ZZZ0001")
        assert extract_case_guids(html, _CASE_NO) == []

    def test_no_hit_returns_empty(self):
        assert extract_case_guids(_list_page_html(), _CASE_NO) == []


# ──────────── 查询编排（会话自愈链，模拟真实网关/登录页重定向） ────────────


_GATEWAY_CALLBACK_URL = "https://ims.jtn.com/corplink/agw/callback?code=diag-1"
_APP_LOGIN_URL = "https://ims.jtn.com/member/login.aspx?rurl=https%3a%2f%2fims.jtn.com%2fproject"


def _app_login_page_html() -> str:
    """OA 应用层登录页（含 CSRFToken 与账密表单）。"""
    return (
        "<html><body><form>"
        '<input type="hidden" name="CSRFToken" value="csrf-1" />'
        '<input name="userid"><input name="password">'
        "</form></body></html>"
    )


class _SelfHealServer:
    """模拟 ims.jtn.com 前置网关 + OA 应用层的会话语义。

    - 无网关 cookie（corplink_at）访问业务页 → 302 网关回调；
      回调端点 Set-Cookie 下发 corplink_at/it 后 302 回业务页；
    - 有网关 cookie 无应用层会话（ASP.NET_SessionId=ok123）→ 302 应用层登录页；
    - 登录页 POST 账密：成功则 Set-Cookie 应用层会话并 302 回业务页，
      失败（login_error）则停留登录页并渲染错误文案；
    - 带 VIEWSTATE 的搜索 POST → 结果页。
    """

    def __init__(
        self,
        *,
        app_session: str = "ok123",
        login_error: bool = False,
        gateway_dead: bool = False,
        result_guids: tuple[str, ...] = (_GUID_A,),
    ) -> None:
        self.app_session = app_session
        self.login_error = login_error
        self.gateway_dead = gateway_dead
        self.result_guids = result_guids
        self.search_posts = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        cookie = request.headers.get("cookie", "")
        url = str(request.url)

        if "corplink/agw" in url:
            # 模拟回调下发新网关 token（host-only，与旧 .ims.jtn.com 域串不同 → jar 共存）
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
        if "access.jtn.com" in url:
            return httpx.Response(200, text="<html>SSO SPA portal</html>")
        if "member/login.aspx" in url:
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

        # 业务页（列表页 / 搜索）
        has_app_session = f"ASP.NET_SessionId={self.app_session}" in cookie
        if request.method == "GET":
            if has_app_session:
                return httpx.Response(200, text=_list_page_html())
            if "corplink_at=stale" in cookie:
                # 旧网关 token 在 cookie 串里压过新值 → 网关拒绝，弹回调
                return httpx.Response(302, headers=[("Location", _GATEWAY_CALLBACK_URL)])
            if "corplink_at=" in cookie:
                return httpx.Response(302, headers=[("Location", _APP_LOGIN_URL)])
            return httpx.Response(302, headers=[("Location", _GATEWAY_CALLBACK_URL)])

        # 搜索 POST
        self.search_posts += 1
        if has_app_session:
            return httpx.Response(200, text=_result_page_html(*self.result_guids))
        return httpx.Response(302, headers=[("Location", _APP_LOGIN_URL)])


class TestLookupCaseGuids:
    @pytest.mark.asyncio
    async def test_empty_keyword_skips_network(self):
        server = _SelfHealServer()
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return server.handler(request)

        script, _ = _make_script(handler)
        assert await script.lookup_case_guids("   ") == []
        assert calls["n"] == 0

    @pytest.mark.asyncio
    async def test_fresh_cached_session_direct_hit(self):
        """缓存会话新鲜：GET 直达列表页，无需自愈与 http_login。"""
        server = _SelfHealServer()
        cached = [{"name": "ASP.NET_SessionId", "value": "ok123", "domain": "ims.jtn.com", "path": "/"}]
        script, http_login = _make_script(server.handler, cached_cookies=cached)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert server.search_posts == 1
        http_login.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stale_cache_self_heals_via_gateway_then_form_login(self):
        """缓存失效：网关回调 Set-Cookie 自愈 → 应用层账密登录 → 搜索成功。

        复现 2026-10-06 线上问题的修复路径（旧实现在此场景误报缺 __VIEWSTATE）。
        """
        server = _SelfHealServer()
        cached = [{"name": "ASP.NET_SessionId", "value": "stale", "domain": "ims.jtn.com", "path": "/"}]
        script, _ = _make_script(server.handler, cached_cookies=cached)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert server.search_posts == 1

    @pytest.mark.asyncio
    async def test_no_cache_also_self_heals(self):
        """无缓存冷启动：同样走网关自愈 + 表单登录。"""
        server = _SelfHealServer()
        script, _ = _make_script(server.handler, cached_cookies=None)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]

    @pytest.mark.asyncio
    async def test_stale_gateway_cookie_does_not_block_self_heal(self):
        """缓存里残留已失效的网关 token：自愈前必须清掉，否则与新下发值共存死循环。

        复现 2026-10-06 admin 进程「每轮新 code 弹回调」问题。
        """
        server = _SelfHealServer()
        cached = [
            {"name": "ASP.NET_SessionId", "value": "stale", "domain": "ims.jtn.com", "path": "/"},
            {"name": "corplink_at", "value": "stale", "domain": ".ims.jtn.com", "path": "/"},
            {"name": "corplink_it", "value": "stale", "domain": ".ims.jtn.com", "path": "/"},
        ]
        script, _ = _make_script(server.handler, cached_cookies=cached)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert server.search_posts == 1

    @pytest.mark.asyncio
    async def test_multi_hit(self):
        server = _SelfHealServer(result_guids=(_GUID_B, _GUID_A, _GUID_B))
        script, _ = _make_script(server.handler)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_B, _GUID_A]

    @pytest.mark.asyncio
    async def test_no_hit_returns_empty_list(self):
        server = _SelfHealServer(result_guids=())
        script, _ = _make_script(server.handler)
        assert await script.lookup_case_guids(_CASE_NO) == []

    @pytest.mark.asyncio
    async def test_login_failure_raises_account_error(self):
        server = _SelfHealServer(login_error=True)
        script, _ = _make_script(server.handler)
        with pytest.raises(RuntimeError, match="账号或密码错误"):
            await script.lookup_case_guids(_CASE_NO)

    @pytest.mark.asyncio
    async def test_gateway_dead_loop_raises(self):
        """网关死拦（回调不下发会话）→ 明确报「会话无法建立」。"""
        server = _SelfHealServer(gateway_dead=True)
        script, _ = _make_script(server.handler)
        with pytest.raises(RuntimeError, match="会话无法建立"):
            await script.lookup_case_guids(_CASE_NO)

    @pytest.mark.asyncio
    async def test_session_expired_mid_search_retries_once(self):
        """搜索时会话突然失效：整体重试一次后成功。"""
        server = _SelfHealServer()
        original = server.handler
        state = {"expired_once": False}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and "member/login.aspx" not in str(request.url):
                if not state["expired_once"]:
                    state["expired_once"] = True
                    return httpx.Response(302, headers=[("Location", _APP_LOGIN_URL)])
            return original(request)

        script, _ = _make_script(handler)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert state["expired_once"] is True  # 首次搜索触发过会话失效
        assert server.search_posts == 1  # 重试后的成功搜索

    @pytest.mark.asyncio
    async def test_plain_page_without_viewstate_raises(self):
        """无任何登录/网关特征但拿不到 VIEWSTATE → 会话无法建立。"""
        server = _SelfHealServer()
        script, _ = _make_script(lambda request: httpx.Response(200, text="<html><body>异常页</body></html>"))
        with pytest.raises(RuntimeError, match="会话无法建立"):
            await script.lookup_case_guids(_CASE_NO)


# ──────────── 调度器装配 ────────────


class TestLookupOaCaseGuidExecutor:
    def _make_user(self) -> MagicMock:
        return MagicMock(id=1)

    def test_missing_credential_raises(self):
        from apps.oa_filing.services import script_executor_service as mod

        service = mod.ScriptExecutorService()
        with patch.object(mod.ScriptExecutorService, "_find_credential", return_value=None):
            with pytest.raises(RuntimeError, match="未找到匹配凭证"):
                service.lookup_oa_case_guid(case_no=_CASE_NO, user=self._make_user())

    def test_success_returns_guids(self):
        import asyncio

        from apps.oa_filing.services import script_executor_service as mod

        adapter = MagicMock()
        captured: dict[str, Any] = {}

        async def fake_lookup(case_no: str, credential: Any) -> list[str]:
            captured["case_no"] = case_no
            captured["credential"] = credential
            return [_GUID_A]

        adapter.lookup_case_guid = fake_lookup
        credential = MagicMock(account="acc", password="p")

        with (
            patch.object(mod.ScriptExecutorService, "_find_credential", return_value=credential),
            patch.object(mod, "create_adapter", return_value=adapter) as mock_create,
            patch.object(mod, "run_coro_sync", side_effect=lambda coro, **kw: asyncio.run(coro)),
        ):
            result = mod.ScriptExecutorService().lookup_oa_case_guid(case_no=f"  {_CASE_NO}  ", user=self._make_user())

        assert result == [_GUID_A]
        assert captured["case_no"] == _CASE_NO  # strip 生效
        assert captured["credential"] is credential
        mock_create.assert_called_once_with("金诚同达OA", "acc", "p")

    def test_error_mapped_to_friendly_message(self):
        import asyncio

        from apps.oa_filing.services import script_executor_service as mod

        adapter = MagicMock()

        async def fake_lookup(case_no: str, credential: Any) -> list[str]:
            raise RuntimeError("Read timed out")

        adapter.lookup_case_guid = fake_lookup
        credential = MagicMock(account="acc", password="p")

        with (
            patch.object(mod.ScriptExecutorService, "_find_credential", return_value=credential),
            patch.object(mod, "create_adapter", return_value=adapter),
            patch.object(mod, "run_coro_sync", side_effect=lambda coro, **kw: asyncio.run(coro)),
        ):
            with pytest.raises(RuntimeError, match="VPN"):
                mod.ScriptExecutorService().lookup_oa_case_guid(case_no=_CASE_NO, user=self._make_user())

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
