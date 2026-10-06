"""JtnCaseGuidScript（案号查 GUID，案件选择对话框 GET 搜索）单测（无网络）。

覆盖：对话框 URL 构造、radio GUID 提取（lxml 主路径 + 正则兜底）、
完整查询编排（命中/多命中/0 命中/会话自愈链/登录失败/会话中途失效重试）、
三字段入口（案号/案名/客户名）的参数与 Referer、
ScriptExecutorService 三个查询入口的装配与错误映射。
HTTP 全部走 httpx.MockTransport 或实例打桩。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from apps.oa_filing.services.oa_scripts.jtn.case_guid.constants import _DIALOG_CATEGORY, _DIALOG_REFERER, _DIALOG_URL
from apps.oa_filing.services.oa_scripts.jtn.case_guid.service import (
    JtnCaseGuidScript,
    dialog_search_url,
    extract_dialog_guids,
)
from apps.oa_filing.services.oa_scripts.jtn.http_session import is_oa_login_page

_GUID_A = "b0219b56-3968-48a8-8e12-3ca86bf160ce"
_GUID_B = "0f2b7a11-1111-2222-3333-444455556666"
_GUID_C = "B0219B56-3968-48A8-8E12-3CA86BF160CE"  # 大写形态，提取时应归一为小写

_CASE_NO = "2026TEST0001"
_DIALOG_SEARCH_URL = f"{_DIALOG_URL}?category={_DIALOG_CATEGORY}&project_no={_CASE_NO}"


def _dialog_form_html() -> str:
    """对话框搜索表单（会话有效性的页面特征）。"""
    return '<html><body><form><input id="project_no" name="project_no" type="text" value="" /></form></body></html>'


def _dialog_results_html(*guids: str) -> str:
    rows = "".join(
        f'<tr><td>选择</td><td>{_CASE_NO}</td><td><input type="radio" name="Project" value="{g}" /></td></tr>'
        for g in guids
    )
    return f"<html><body><form>{_dialog_form_html()}<table>{rows}</table></form></body></html>"


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

    script._build_client = _build_client  # type: ignore[assignment, method-assign]
    return script, http_login


# ──────────── URL 构造 ────────────


class TestDialogSearchUrl:
    def test_case_no_url(self):
        url = dialog_search_url(param_name="project_no", keyword="2026GZM0286")
        parsed = urlparse(url)
        assert f"{parsed.netloc}{parsed.path}" == "ims.jtn.com/searchdlg/searchProject.aspx"
        query = parse_qs(parsed.query)
        assert query == {"category": ["OfficeDOC"], "project_no": ["2026GZM0286"]}

    def test_keyword_is_urlencoded(self):
        parsed = parse_qs(urlparse(dialog_search_url(param_name="project_name", keyword="某公司 合同纠纷")).query)
        assert parsed["project_name"] == ["某公司 合同纠纷"]


# ──────────── GUID 提取 ────────────


class TestExtractDialogGuids:
    def test_single(self):
        assert extract_dialog_guids(_dialog_results_html(_GUID_A)) == [_GUID_A]

    def test_multi_keeps_order_and_dedupes(self):
        html = _dialog_results_html(_GUID_B, _GUID_A, _GUID_B)
        assert extract_dialog_guids(html) == [_GUID_B, _GUID_A]

    def test_guid_value_lowercased(self):
        assert extract_dialog_guids(_dialog_results_html(_GUID_C)) == [_GUID_A]

    def test_non_radio_guids_ignored(self):
        # 非 radio 的 GUID（如普通链接 keyid）不参与提取，防误报
        html = (
            "<html><body><form>"
            '<input id="project_no" name="project_no" />'
            f"<a href='/project/projectView.aspx?keyid={_GUID_B}'>查看</a>"
            "</form></body></html>"
        )
        assert extract_dialog_guids(html) == []

    def test_no_radio_returns_empty(self):
        assert extract_dialog_guids(_dialog_form_html()) == []

    def test_unparseable_html_falls_back_to_regex(self):
        broken = f'<input type="radio" value="{_GUID_A}"'
        with patch(
            "apps.oa_filing.services.oa_scripts.jtn.case_guid.service.lxml_html.fromstring",
            side_effect=ValueError("boom"),
        ):
            assert extract_dialog_guids(broken) == [_GUID_A]


# ──────────── 登录页判定（http_session 小件接肉眼回归） ────────────


class TestIsOaLoginPage:
    def test_login_url(self):
        assert is_oa_login_page("https://ims.jtn.com/member/login.aspx?rurl=x", "任意内容") is True

    def test_location_replace_placeholder(self):
        assert is_oa_login_page(_DIALOG_URL, _login_page_html()) is True

    def test_normal_dialog_page(self):
        assert is_oa_login_page(_DIALOG_URL, _dialog_results_html(_GUID_A)) is False


# ──────────── 查询编排（会话自愈链，模拟真实网关/登录页重定向） ────────────


_GATEWAY_CALLBACK_URL = "https://ims.jtn.com/corplink/agw/callback?code=diag-1"
_APP_LOGIN_URL = "https://ims.jtn.com/member/login.aspx?rurl=https%3a%2f%2fims.jtn.com%2fsearchdlg"


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

    - 无网关 cookie（corplink_at）访问对话框 → 302 网关回调；
      回调端点 Set-Cookie 下发 corplink_at/it 后 302 回对话框；
    - 有网关 cookie 无应用层会话（ASP.NET_SessionId=ok123）→ 302 应用层登录页；
    - 登录页 POST 账密：成功则 Set-Cookie 应用层会话并 302 回对话框，
      失败（login_error）则停留登录页并渲染错误文案；
    - 带应用层会话的对话框 GET → 搜索结果页（radios）。
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
        self.dialog_hits = 0
        self.last_query: dict[str, list[str]] = {}
        self.last_referer: str = ""
        # 被弹到网关/登录前的业务 URL（回调放行后 302 回这里）
        self.pending_url: str = _DIALOG_SEARCH_URL

    def handler(self, request: httpx.Request) -> httpx.Response:
        cookie = request.headers.get("cookie", "")
        parsed = urlparse(str(request.url))
        host, path = parsed.netloc, parsed.path

        if "corplink/agw" in path:
            # 模拟回调下发新网关 token（host-only，与旧 .ims.jtn.com 域串不同 → jar 共存）
            if self.gateway_dead:
                return httpx.Response(200, text="<html>gateway stuck</html>")
            return httpx.Response(
                302,
                headers=[
                    ("Set-Cookie", "corplink_at=fresh; Path=/"),
                    ("Set-Cookie", "corplink_it=fresh2; Path=/"),
                    ("Location", self.pending_url),
                ],
            )
        if host == "access.jtn.com":
            return httpx.Response(200, text="<html>SSO SPA portal</html>")
        if "member/login.aspx" in path:
            if request.method == "POST":
                if self.login_error:
                    return httpx.Response(200, text='<input name="userid"><input name="password">账号或密码错误')
                return httpx.Response(
                    302,
                    headers=[
                        ("Set-Cookie", f"ASP.NET_SessionId={self.app_session}; Path=/"),
                        # 真实 rurl 语义：带完整查询参数弹回原业务 URL
                        ("Location", self.pending_url),
                    ],
                )
            return httpx.Response(200, text=_app_login_page_html())

        # 对话框搜索（GET）：记录完整业务 URL（含查询参数），供网关/登录放行后弹回
        self.pending_url = str(request.url)
        has_app_session = f"ASP.NET_SessionId={self.app_session}" in cookie
        if has_app_session:
            self.dialog_hits += 1
            self.last_query = parse_qs(parsed.query)
            self.last_referer = request.headers.get("referer", "")
            return httpx.Response(200, text=_dialog_results_html(*self.result_guids))
        if "corplink_at=stale" in cookie:
            # 旧网关 token 在 cookie 串里压过新值 → 网关拒绝，弹回调
            return httpx.Response(302, headers=[("Location", _GATEWAY_CALLBACK_URL)])
        if "corplink_at=" in cookie:
            return httpx.Response(302, headers=[("Location", _APP_LOGIN_URL)])
        return httpx.Response(302, headers=[("Location", _GATEWAY_CALLBACK_URL)])


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
        """缓存会话新鲜：单次 GET 直达对话框结果页，无需自愈与 http_login。"""
        server = _SelfHealServer()
        cached = [{"name": "ASP.NET_SessionId", "value": "ok123", "domain": "ims.jtn.com", "path": "/"}]
        script, http_login = _make_script(server.handler, cached_cookies=cached)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert server.dialog_hits == 1
        http_login.assert_not_awaited()
        # 搜索参数与 Referer 随请求携带
        assert server.last_query == {"category": [_DIALOG_CATEGORY], "project_no": [_CASE_NO]}
        assert server.last_referer == _DIALOG_REFERER

    @pytest.mark.asyncio
    async def test_stale_cache_self_heals_via_gateway_then_form_login(self):
        """缓存失效：网关回调 Set-Cookie 自愈 → 应用层账密登录 → 搜索成功。

        复现 2026-10-06 线上问题的修复路径（会话自愈链与页面无关，对话框
        切换后应原样保留）。
        """
        server = _SelfHealServer()
        cached = [{"name": "ASP.NET_SessionId", "value": "stale", "domain": "ims.jtn.com", "path": "/"}]
        script, _ = _make_script(server.handler, cached_cookies=cached)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert server.dialog_hits == 1

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
        assert server.dialog_hits == 1

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
            if "searchdlg/searchProject.aspx" in str(request.url) and not state["expired_once"]:
                state["expired_once"] = True
                return httpx.Response(302, headers=[("Location", _APP_LOGIN_URL)])
            return original(request)

        script, _ = _make_script(handler)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert state["expired_once"] is True  # 首次搜索触发过会话失效
        assert server.dialog_hits == 1  # 重试后的成功搜索

    @pytest.mark.asyncio
    async def test_plain_page_without_form_marker_raises(self):
        """无任何登录/网关特征但拿不到对话框表单 → 会话无法建立。"""
        script, _ = _make_script(lambda request: httpx.Response(200, text="<html><body>异常页</body></html>"))
        with pytest.raises(RuntimeError, match="会话无法建立"):
            await script.lookup_case_guids(_CASE_NO)


class TestLookupByOtherFields:
    """案名 / 客户名入口：同一对话框、同一会话链，仅查询参数不同。"""

    @pytest.mark.asyncio
    async def test_by_name_sends_project_name_param(self):
        server = _SelfHealServer()
        script, _ = _make_script(server.handler)
        assert await script.lookup_case_guids_by_name("某公司 合同纠纷") == [_GUID_A]
        assert server.last_query == {"category": [_DIALOG_CATEGORY], "project_name": ["某公司 合同纠纷"]}

    @pytest.mark.asyncio
    async def test_by_customer_name_sends_customer_param(self):
        server = _SelfHealServer()
        script, _ = _make_script(server.handler)
        assert await script.lookup_case_guids_by_customer_name("腾讯") == [_GUID_A]
        assert server.last_query == {"category": [_DIALOG_CATEGORY], "project_customer_name": ["腾讯"]}

    @pytest.mark.asyncio
    async def test_by_name_self_heals_too(self):
        """案名入口同样走完整自愈链（缓存失效场景）。"""
        server = _SelfHealServer()
        cached = [{"name": "ASP.NET_SessionId", "value": "stale", "domain": "ims.jtn.com", "path": "/"}]
        script, _ = _make_script(server.handler, cached_cookies=cached)
        assert await script.lookup_case_guids_by_name("某案名") == [_GUID_A]
        assert server.dialog_hits == 1


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
            patch.object(mod.ScriptExecutorService, "_find_credential", return_value=credential),
            patch.object(mod, "create_adapter", return_value=adapter) as mock_create,
            patch.object(mod, "run_coro_sync", side_effect=lambda coro, **kw: asyncio.run(coro)),
        ):
            result = getattr(mod.ScriptExecutorService(), method_name)(keyword, user=self._make_user())
        assert mock_create.call_args[0] == ("金诚同达OA", "acc", "p")
        return result

    def test_missing_credential_raises(self):
        from apps.oa_filing.services import script_executor_service as mod

        service = mod.ScriptExecutorService()
        with patch.object(mod.ScriptExecutorService, "_find_credential", return_value=None):
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
