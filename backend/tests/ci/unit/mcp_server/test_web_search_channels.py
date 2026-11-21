"""搜索三通道（桌面 → 手机 → 兜底引擎）与韧性状态的行为测试。

## 这些用例守的是什么

2026-11-21 实测：搜狗免费 HTML 搜索是 **IP 级**封禁（302 → ``/captcha/``），
共享 MCP 下全所共用一个出口 IP；生产库近 7 天真实调用 33 拦 / 6 成（15%）。
当时的三个放大器在代码里都有对应用例：

1. **没有熔断** → 模型看到「被反爬」就换个关键词再打（生产库会话 268 三分钟
   连打 20 次全拦）→ ``TestBreaker`` / ``test_desktop_blocked_falls_back_to_mobile``；
2. **没有结果缓存** → 多答双 lane 同题各搜一次 → ``TestResultCache`` /
   ``test_second_identical_query_hits_cache``；
3. **单引擎 = 单点** → 桌面被封就全所不能搜 → ``TestChannelFallback``
   （手机通道在封禁期间仍可用，实测 307KB 结果页）。

兜底引擎（律所百炼）来源以自媒体为主且**无发布日期**，所以另有一组用例守
「按权威性重排 + 无官方来源时显式声明」——不能让模型把百家号当法源。
"""

from __future__ import annotations

import collections
import importlib
import json
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest import mock

import httpx
import pytest


def _module() -> Any:
    return importlib.import_module("mcp_server.tools.web_search.web_search")


def _firm_module() -> Any:
    return importlib.import_module("mcp_server.firm_search")


def _resilience() -> Any:
    return importlib.import_module("mcp_server.tools.web_search.resilience")


def _response(text: str, url: str = "https://www.sogou.com/web") -> httpx.Response:
    return httpx.Response(status_code=200, content=text.encode("utf-8"), request=httpx.Request("GET", url))


class _FakeClient:
    """替身 HTTP 客户端：记录调用、按序吐出预置响应。

    不用 ``MagicMock`` 套 ``.__enter__.return_value``：那层嵌套在 ``with``
    语句里极易把断言打到「另一个 mock 实例」上（实测踩过一次：调用明明发生
    了，``call_count`` 却是 0）。显式类让「打了几次、打了谁」一目了然。
    """

    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses  # 共享同一个列表：后续 with 语句继续消费剩下的
        self.get_calls: list[tuple[str, dict[str, Any]]] = []
        self.post_calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def _next(self) -> httpx.Response:
        if not self.responses:
            raise AssertionError("预置响应已用尽——调用次数超出预期")
        return self.responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        self.get_calls.append((url, kwargs))
        return self._next()

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.post_calls.append((url, kwargs))
        return self._next()

    def stream(self, method: str, url: str, **kwargs: Any) -> Any:
        self.post_calls.append((url, kwargs))
        return _FakeStream(self._next())


class _FakeStream:
    """``client.stream(...)`` 的替身：暴露 status_code / iter_raw / charset_encoding。"""

    def __init__(self, response: httpx.Response) -> None:
        self.status_code = response.status_code
        self._body = response.content
        self.charset_encoding = "utf-8"

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def iter_raw(self, chunk_size: int | None = None) -> Iterator[bytes]:
        yield self._body


@pytest.fixture()
def fake_http() -> Iterator[dict[str, Any]]:
    """替换 ``httpx.Client``，用例里往 ``state['responses']`` 塞预置响应。

    补丁打在**共享的 httpx 模块**上：搜狗通道与兜底引擎通道各自 ``import
    httpx``，打模块属性才能一次覆盖两条链路（也顺带保证用例不触网）。
    """
    state: dict[str, Any] = {"responses": [], "client": None}

    def _factory(*args: Any, **kwargs: Any) -> _FakeClient:
        # 整轮用例共用一个替身：多通道串行时调用记录要累积在同一处，
        # 否则断言只能看到「最后一个 with 里的那次请求」。
        if state["client"] is None:
            state["client"] = _FakeClient(state["responses"])
        return state["client"]

    with mock.patch.object(httpx, "Client", side_effect=_factory):
        yield state


DESKTOP_OK = (
    "<html><body>"
    '<div class="vrwrap"><h3><a href="/link?url=abc">桌面结果甲</a></h3>'
    '<div class="space-txt">桌面摘要甲</div></div>'
    "</body></html>"
)
ANTISPIDER = "<html><body>请输入下方验证码完成安全验证</body></html>"

MOBILE_OK = """
<html><body>
  <div class="hint"><div class="hint-box-title"><h3>大家还在搜</h3></div></div>
  <div class="card_normal_result__cardFrame_a7e7">
    <a class="link__saLink_b05d"
       href="./id=xx&amp;url=https%3A%2F%2Fnews.cnr.cn%2Fnative%2F20260112%2Ft1.shtml&amp;clk=3">
      <div class="sa-spacing-text-heading"><h3>试用期可随意解聘_央广网</h3></div>
    </a>
    <div>根据《劳动合同法》第十九条规定,试用期包含在劳动合同期限内。 央广网 2026-01-12</div>
  </div>
  <div class="card_normal_result__cardFrame_a7e7">
    <a class="link__saLink_b05d"
       href="./id=xx&amp;url=https%3A%2F%2Fnews.cnr.cn%2Fnative%2F20260112%2Ft1.shtml&amp;clk=6">
      <div><h3>重复卡（同一条结果的正文卡）</h3></div>
    </a>
    <div>同一 URL 的正文片段 央广网 2026-01-12</div>
  </div>
  <div class="card_normal_result__cardFrame_a7e7">
    <a class="link__saLink_b05d"
       href="./id=yy&amp;url=https%3A%2F%2Fm.suichuan.gov.cn%2Fxxgk-show-10299913.html">
      <div><h3>遂川县人民政府-以案释法</h3></div>
    </a>
    <div>《劳动合同法》第十九条 遂川县人民政府网 2025-07-14</div>
  </div>
</body></html>
"""


class TestBreaker:
    """熔断冷却：失败后短时间内不得再打同一个通道。"""

    def test_trip_opens_and_expires(self) -> None:
        now = [1000.0]
        breaker = _resilience().ChannelBreaker(clock=lambda: now[0])

        breaker.trip("sogou_desktop", "被反爬", 600)
        remaining, reason = breaker.info("sogou_desktop")
        assert 599 <= remaining <= 600
        assert reason.startswith("被反爬")  # 附「第 N 次，冷却 ×M」便于运维辨认
        assert breaker.is_open("sogou_desktop")

        now[0] += 601
        assert breaker.info("sogou_desktop") == (0.0, "")
        assert not breaker.is_open("sogou_desktop")

    def test_repeat_trip_keeps_later_deadline(self) -> None:
        now = [0.0]
        breaker = _resilience().ChannelBreaker(clock=lambda: now[0])
        breaker.trip("c", "短", 10)
        breaker.trip("c", "长", 600)
        assert breaker.info("c")[0] > 500
        # 更短的 trip 不能缩短已有冷却
        breaker.trip("c", "更短", 1)
        assert breaker.info("c")[0] > 500

    def test_channels_are_independent(self) -> None:
        breaker = _resilience().ChannelBreaker()
        breaker.trip("sogou_desktop", "被反爬", 600)
        assert breaker.is_open("sogou_desktop")
        assert not breaker.is_open("sogou_mobile")

    def test_repeated_failures_escalate_cooldown(self) -> None:
        """同一通道连续失败：冷却按 2× 递增，封顶 4×（实测封禁 ≥10 分钟，一次 600s 不够）。"""
        now = [0.0]
        breaker = _resilience().ChannelBreaker(clock=lambda: now[0])

        breaker.trip("c", "被反爬", 600)
        first = breaker.info("c")[0]
        now[0] += first + 1
        breaker.trip("c", "被反爬", 600)
        second = breaker.info("c")[0]
        now[0] += second + 1
        breaker.trip("c", "被反爬", 600)
        third = breaker.info("c")[0]
        now[0] += third + 1
        breaker.trip("c", "被反爬", 600)
        fourth = breaker.info("c")[0]

        assert 599 <= first <= 600
        assert 1199 <= second <= 1200
        assert 2399 <= third <= 2400
        assert 2399 <= fourth <= 2400, "封顶 4×"
        assert breaker.strikes["c"] == 4

    def test_success_resets_strikes(self) -> None:
        breaker = _resilience().ChannelBreaker()
        breaker.trip("c", "x", 60)
        breaker.clear("c")

        breaker.trip("c", "x", 60)

        assert breaker.strikes["c"] == 1, "恢复后重新计数（否则冷却会越滚越长）"
        assert breaker.info("c")[0] <= 61

    def test_zero_cooldown_is_noop(self) -> None:
        breaker = _resilience().ChannelBreaker()
        breaker.trip("c", "x", 0)
        assert not breaker.is_open("c")


class TestResultCache:
    """结果缓存：双 lane 同题只该真正检索一次。"""

    def test_put_get_and_expire(self) -> None:
        now = [0.0]
        cache = _resilience().ResultCache(ttl=600, clock=lambda: now[0])
        key = cache.key("  劳动合同  ", 1, 5)
        cache.put(key, "结果")

        assert cache.get(key) == "结果"
        now[0] += 601
        assert cache.get(key) is None

    def test_key_is_normalized(self) -> None:
        cache = _resilience().ResultCache()
        assert cache.key("合同", 1, 5) == cache.key("  合同 ", 1, 5)
        assert cache.key("合同", 1, 5) != cache.key("合同", 2, 5)

    def test_lru_eviction(self) -> None:
        cache = _resilience().ResultCache(max_entries=2)
        cache.put(cache.key("a", 1, 5), "A")
        cache.put(cache.key("b", 1, 5), "B")
        cache.put(cache.key("c", 1, 5), "C")
        assert cache.get(cache.key("a", 1, 5)) is None
        assert cache.get(cache.key("c", 1, 5)) == "C"


class TestChannelFallback:
    """桌面被封 → 手机顶上；两者都不行 → 兜底引擎；全挂 → 如实归因。"""

    def test_desktop_blocked_falls_back_to_mobile(self, fake_http: dict[str, Any]) -> None:
        module = _module()
        fake_http["responses"] = [_response(ANTISPIDER), _response(MOBILE_OK, "https://wap.sogou.com/x")]

        text = module._do_search("试用期", 5)

        assert "手机端" in text
        assert "news.cnr.cn" in text
        assert "2026-01-12" in text  # 手机通道同样带来源与日期
        assert len(fake_http["client"].get_calls) == 2  # 桌面 + 手机各一次
        remaining, reason = module._BREAKER.info(module.CHANNEL_DESKTOP)
        assert remaining > 300 and "反爬" in reason  # 桌面被熔断约 10 分钟

    def test_open_breaker_skips_network_entirely(self, fake_http: dict[str, Any]) -> None:
        module = _module()
        module._BREAKER.trip(module.CHANNEL_DESKTOP, "被反爬", 600)
        fake_http["responses"] = [_response(MOBILE_OK, "https://wap.sogou.com/x")]

        text = module._do_search("试用期", 5)

        assert len(fake_http["client"].get_calls) == 1  # 桌面通道根本没发请求
        assert "手机端" in text

    def test_second_identical_query_hits_cache(self, fake_http: dict[str, Any]) -> None:
        module = _module()
        fake_http["responses"] = [_response(DESKTOP_OK)]

        first = module._do_search("合同", 5)
        client = fake_http["client"]
        second = module._do_search("合同", 5)

        assert first == second
        assert len(client.get_calls) == 1  # 第二次没再打网络
        assert "桌面结果甲" in first

    def test_all_channels_failed_message_is_honest_and_unwrapped(self) -> None:
        module = _module()
        with (
            mock.patch.object(
                module,
                "_desktop_search",
                return_value=module._Outcome(
                    False,
                    detail="搜索被反爬/验证码拦截，本次未获取到结果；建议稍后再试。",
                    reason="antispider",
                    cooldown=600,
                ),
            ),
            mock.patch.object(
                module,
                "_mobile_search",
                return_value=module._Outcome(False, detail="手机通道解析异常。", reason="parse_zero", cooldown=300),
            ),
            mock.patch.object(module, "_firm_search_outcome", return_value=None),
        ):
            text = module._do_search("合同", 5)

        assert module._WRAPPER_HEADER not in text  # 本系统文本，不套外部内容包裹
        assert "已尝试" in text
        assert "搜狗桌面通道" in text and "搜狗手机通道" in text
        assert "反爬" in text
        assert "不代表互联网上没有相关信息" in text

    def test_pagination_uses_desktop_only(self) -> None:
        module = _module()
        assert module._mobile_search("合同", 5, page=2) is None
        assert module._firm_search_outcome("合同", 5, page=2) is None


class TestMobileParser:
    """手机端 DOM 是哈希类名：解析必须带「按真实地址去重」与日期抽取。"""

    def test_parses_titles_real_urls_dates(self) -> None:
        module = _module()
        results = module._parse_mobile_results(MOBILE_OK, 5)

        assert len(results) == 2  # 同一 URL 的标题卡+正文卡被去重
        assert results[0].title == "试用期可随意解聘_央广网"
        assert results[0].url == "https://news.cnr.cn/native/20260112/t1.shtml"
        assert results[0].source == "news.cnr.cn"
        assert results[0].freshness == "2026-01-12"

    def test_link_target_rejects_non_http(self) -> None:
        module = _module()
        assert module._mobile_link_target("./id=x&url=javascript:alert(1)") == ""
        assert module._mobile_link_target("./id=x&pcurl=https%3A%2F%2Fa.gov.cn%2Fb") == "https://a.gov.cn/b"

    def test_empty_html_parses_to_nothing(self) -> None:
        module = _module()
        assert module._parse_mobile_results("<html><body>请完成验证</body></html>", 5) == []


class TestFirmFallback:
    """兜底引擎：解析 SSE、按权威性重排、无官方来源时显式提醒、摘要必须截断。"""

    @pytest.fixture(autouse=True)
    def _firm_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        # 显式走「环境变量覆盖」分支：这些用例验的是协议解析，不该读库
        monkeypatch.setenv(module.ENV_URL, "http://gw:4000/WebSearch/mcp")
        monkeypatch.setenv(module.ENV_KEY, "Bearer test-key")
        monkeypatch.setattr(module, "_active_providers", list)

    @staticmethod
    def _sse(pages: list[dict[str, Any]]) -> httpx.Response:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": json.dumps({"status": 0, "pages": pages}, ensure_ascii=False)}]
            },
        }
        return _response(f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n")

    @staticmethod
    def _config() -> Any:
        return _firm_module().FirmSearchConfig(url="http://gw:4000/WebSearch/mcp", keys=("k",), timeout=45)

    def test_parses_sse_pages(self, fake_http: dict[str, Any]) -> None:
        page = {"title": "T", "url": "https://www.court.gov.cn/a", "hostname": "最高人民法院", "snippet": "S"}
        fake_http["responses"] = [self._sse([page])]

        out = _firm_module().search("合同", 5, self._config())

        assert out["ok"] is True
        assert out["pages"] == [page]
        assert fake_http["client"].post_calls[0][1]["headers"]["x-litellm-api-key"] == "Bearer k"

    def test_rpc_error_reported(self, fake_http: dict[str, Any]) -> None:
        fake_http["responses"] = [_response('event: message\ndata: {"jsonrpc":"2.0","id":1,"error":{"message":"boom"}}\n\n')]

        out = _firm_module().search("合同", 5, self._config())

        assert out["ok"] is False
        assert out["reason"] == "rpc_error"

    def test_empty_pages_reported(self, fake_http: dict[str, Any]) -> None:
        fake_http["responses"] = [self._sse([])]

        out = _firm_module().search("合同", 5, self._config())

        assert out["ok"] is False
        assert out["reason"] == "empty"

    def test_missing_config_skips_silently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_firm_module().ENV_URL, raising=False)
        monkeypatch.delenv(_firm_module().ENV_KEY, raising=False)
        assert _firm_module().load_config() is None
        assert _module()._firm_search_outcome("合同", 5, 1) is None

    def test_authority_sorting_no_warning_when_official_present(self, fake_http: dict[str, Any]) -> None:
        fake_http["responses"] = [
            self._sse(
                [
                    {"title": "自媒体", "url": "https://baijiahao.baidu.com/s?id=1", "hostname": "百度", "snippet": "x"},
                    {
                        "title": "官方",
                        "url": "https://www.mohrss.gov.cn/a",
                        "hostname": "人力资源和社会保障部",
                        "snippet": "y",
                    },
                ]
            )
        ]

        out = _module()._firm_search_outcome("合同", 5, 1)

        assert out is not None and out.ok
        assert out.text.index("人力资源和社会保障部") < out.text.index("百度")
        assert "多为自媒体" not in out.text

    def test_warning_when_only_self_media(self, fake_http: dict[str, Any]) -> None:
        fake_http["responses"] = [
            self._sse([{"title": "自媒体", "url": "https://www.sohu.com/a/1", "hostname": "搜狐", "snippet": "x"}])
        ]

        out = _module()._firm_search_outcome("合同", 5, 1)

        assert out is not None and out.ok
        assert "多为自媒体" in out.text
        assert "不得直接作为法源" in out.text

    def test_long_snippet_truncated(self, fake_http: dict[str, Any]) -> None:
        fake_http["responses"] = [
            self._sse([{"title": "长文", "url": "https://www.sohu.com/a/2", "hostname": "搜狐", "snippet": "法" * 5000}])
        ]

        out = _module()._firm_search_outcome("合同", 5, 1)

        assert out is not None and out.ok
        assert "摘要过长已截断" in out.text
        assert len(out.text.encode("utf-8")) <= _module()._OUTPUT_BYTE_BUDGET


class TestResultShaping:
    """输出整形：权威性分层、提醒只在必要时出现、字节预算不得越线。"""

    def test_authority_tiers(self) -> None:
        module = _module()
        assert module._authority_tier("www.court.gov.cn") == 0
        assert module._authority_tier("flk.npc.gov.cn") == 0
        assert module._authority_tier("www.pkulaw.com") == 1
        assert module._authority_tier("baijiahao.baidu.com") == 2
        assert module._authority_tier("example.com") == 3

    def test_authority_note_only_when_no_authoritative(self) -> None:
        module = _module()
        assert module._authority_note(["www.court.gov.cn", "baijiahao.baidu.com"]) == ""
        assert "不得直接作为法源" in module._authority_note(["baijiahao.baidu.com"])

    def test_output_respects_byte_budget(self) -> None:
        module = _module()
        results = [
            module._SearchResult(title=f"标题{i}", url=f"https://a.gov.cn/{i}", snippet="摘" * 400) for i in range(20)
        ]

        text = module._cap_output(results, 1)

        assert len(text.encode("utf-8")) <= module._OUTPUT_BYTE_BUDGET
        assert text.startswith(module._WRAPPER_HEADER)
        assert text.endswith(module._WRAPPER_FOOTER)


class TestConfigResolution:
    """地址与凭据从哪来：**复用 Admin「AI 平台」配置**，不再配第二份密钥。

    这是 2026-11-21 的返工点：第一版把网关地址和 key 写进 .env（``FACHUAN_FIRM_SEARCH_KEY``），
    而同一把 key 本来就配在 Admin → AI 平台（``LLMProvider``）里，等于把密钥配了两份：
    换 key 要改两处、轮换漏一处就静默失效。现在默认从平台配置推导，
    key 走**与模型调用同一个** Key 池（并发上限与失败冷却都共享）。
    """

    class _Provider:
        """``OpenAIProviderConfig`` 的替身（字段名与 ``_pick_provider`` 的访问口径一致）。"""

        def __init__(self, **kw: Any) -> None:
            self.name = kw.get("name", "律所 kimi")
            self.base_url = kw.get("base_url", "http://gw.example:4000/v1")
            self.api_keys = kw.get("api_keys", ["sk-a", "sk-b"])
            self.key_model_scopes = kw.get("key_model_scopes", {})
            self.default_model = kw.get("default_model", "kimi-2.6")
            self.enabled = kw.get("enabled", True)
            self.priority = kw.get("priority", 1)
            self.concurrency_per_key = kw.get("concurrency_per_key", 3)

        @property
        def all_models(self) -> list[str]:
            return [self.default_model]

    @pytest.fixture(autouse=True)
    def _no_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        monkeypatch.delenv(module.ENV_URL, raising=False)
        monkeypatch.delenv(module.ENV_KEY, raising=False)
        monkeypatch.delenv(module.ENV_MODEL_HINT, raising=False)
        monkeypatch.delenv(module.ENV_PATH, raising=False)

    def test_mcp_url_derived_from_base_url(self) -> None:
        module = _firm_module()
        assert module.mcp_url_from_base_url("http://gw:4000/v1") == "http://gw:4000/WebSearch/mcp"
        assert module.mcp_url_from_base_url("https://gw.example.com/v1/") == "https://gw.example.com/WebSearch/mcp"
        assert module.mcp_url_from_base_url("http://gw:4000/v1", "/custom/mcp") == "http://gw:4000/custom/mcp"
        # 缺 scheme/host 一律不接：宁可放弃通道，也不要拼个错地址去撞
        assert module.mcp_url_from_base_url("") == ""
        assert module.mcp_url_from_base_url("gw:4000/v1") == ""

    def test_env_override_wins_and_strips_bearer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        monkeypatch.setenv(module.ENV_URL, "http://other:9000/WebSearch/mcp")
        monkeypatch.setenv(module.ENV_KEY, "Bearer sk-env")

        cfg = module.load_config()

        assert cfg is not None
        assert cfg.url == "http://other:9000/WebSearch/mcp"
        assert cfg.keys == ("sk-env",)
        assert cfg.provider == "env-override"

    def test_provider_config_reused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        provider = self._Provider()
        monkeypatch.setattr(module, "_active_providers", lambda: [provider])

        cfg = module.load_config()

        assert cfg is not None
        # URL 由平台 base_url 推导（不是第二处配置）
        assert cfg.url == "http://gw.example:4000/WebSearch/mcp"
        # key 用平台的全部 key（不再单配一把）
        assert cfg.keys == ("sk-a", "sk-b")
        assert cfg.provider == "律所 kimi"
        assert cfg.concurrency_per_key == 3

    def test_provider_without_keys_disables_channel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        monkeypatch.setattr(module, "_active_providers", lambda: [self._Provider(api_keys=[])])
        assert module.load_config() is None

    def test_no_provider_disables_channel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        monkeypatch.setattr(module, "_active_providers", list)
        assert module.load_config() is None

    def test_key_pool_shared_with_model_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """检索与模型调用必须落在**同一个** Key 池实例上。

        各持一份就把「每 Key 并发上限」放大成两倍，直接顶穿网关限额，
        而且失败冷却也不再共享——且这一切都是静默的（不报错）。
        """
        from apps.core.llm.key_pool import shared_pool

        module = _firm_module()
        provider = self._Provider()
        monkeypatch.setattr(module, "_active_providers", lambda: [provider])
        cfg = module.load_config()
        assert cfg is not None

        # 与 openai_compatible._key_pool 逐参数一致
        expected = shared_pool(provider.name, provider.api_keys, provider.concurrency_per_key, None)

        assert module._key_pool(cfg) is expected

    def test_retry_with_next_key_on_401(self, fake_http: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        monkeypatch.setattr(module, "_active_providers", lambda: [self._Provider(api_keys=["sk-1", "sk-2"])])
        cfg = module.load_config()
        assert cfg is not None
        fake_http["responses"] = [
            httpx.Response(401, content=b"", request=httpx.Request("POST", cfg.url)),
            _response("event: message\ndata: " + json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "result": {"content": [{"type": "text", "text": json.dumps(
                    {"status": 0, "pages": [{"title": "T", "url": "https://a.gov.cn/x", "snippet": "s"}]},
                    ensure_ascii=False)}]},
            }, ensure_ascii=False) + "\n\n"),
        ]

        out = module.search("合同", 5, cfg)

        assert out["ok"] is True
        used = [c[1]["headers"]["x-litellm-api-key"] for c in fake_http["client"].post_calls]
        assert used == ["Bearer sk-1", "Bearer sk-2"]  # 换了一把 key，而不是整条通道失败


class TestCallDeadline:
    """SSE 心跳会让「逐次读超时」永不触发——必须自己算总时长。

    2026-11-21 实测血案：某个 key 的检索挂死，``httpx.Client(timeout=45)``
    愣是跑了 **310 秒**才回来，整轮对话被拖死，通道熔断也来不及生效。
    """

    class _DripStream:
        def __init__(self) -> None:
            self.status_code = 200
            self.charset_encoding = "utf-8"

        def __enter__(self) -> _DripStream:
            return self

        def __exit__(self, *exc: Any) -> bool:
            return False

        def iter_raw(self, chunk_size: int | None = None) -> Iterator[bytes]:
            for _ in range(10_000):  # 心跳：每块都「读成功」，但永远读不完
                time.sleep(0.02)
                yield b": keep-alive\n"

    def test_hanging_stream_is_cut_at_deadline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        cfg = module.FirmSearchConfig(url="http://gw/WebSearch/mcp", keys=("k",), timeout=0.3)

        class _Client:
            def __enter__(self) -> _Client:
                return self

            def __exit__(self, *exc: Any) -> bool:
                return False

            def stream(self, method: str, url: str, **kwargs: Any) -> Any:
                return TestCallDeadline._DripStream()

        monkeypatch.setattr(module.httpx, "Client", lambda **kwargs: _Client())

        started = time.monotonic()
        out = module.search("合同", 5, cfg)
        elapsed = time.monotonic() - started

        assert out["ok"] is False
        assert out["reason"] == "timeout"
        assert elapsed < 3.0, f"必须在截止时刻附近截断，实测 {elapsed:.2f}s"


class TestAdaptiveLimiter:
    """自适应并发调度：上限 = key 数 × 每 key 并发，实际放行按实测延迟自调。

    背景（2026-11-21 实测）：10 把 key × 每把 3 并发 = 硬上限 30，但把 30 个请求
    同时放出去上游顶不住——30 并发时 27% 返回空 pages、p50 21s；10 并发时全成、2.8s。
    写死任何一个数都会在某种负载下变成错的，所以用窗口采样自己找水位。
    """

    def _limiter(self, **kw: Any) -> Any:
        module = importlib.import_module("mcp_server.adaptive_limiter")
        return module.AdaptiveLimiter(**kw)

    @staticmethod
    def _pump(limiter: Any, latency: float, rounds: int) -> None:
        """模拟「有真实并发」的采样：先占住半个窗口的槽位再释放。

        直接 ``release(latency=...)`` 而从不 ``acquire``，在飞数恒为 0，
        会被 app-limited 守卫正确拦下（不涨价）——那样测的就不是增长逻辑了。
        """
        for _ in range(rounds):
            want = max(1, limiter.limit // 2)
            held = 0
            for _ in range(want):
                if limiter.acquire(timeout=0.05):
                    held += 1
            for _ in range(held):
                limiter.release(latency=latency)

    def test_starts_at_safe_level_and_climbs_on_fast_samples(self) -> None:
        limiter = self._limiter(max_limit=30, initial=10, window=4)

        assert limiter.limit == 10  # 起步 = 每 key 1 并发（实测安全水位）
        self._pump(limiter, 0.05, 4 * 40)
        assert limiter.limit == 30, "延迟贴近底噪时应爬到硬上限（吃满所有 key）"

    def test_halves_when_latency_jumps(self) -> None:
        limiter = self._limiter(max_limit=30, window=4)
        self._pump(limiter, 0.05, 4 * 40)  # 先爬到高位
        high = limiter.limit

        self._pump(limiter, 0.05 * 10, 4)  # 一次窗口的「明显排队」样本
        assert limiter.limit < high, "延迟翻十倍时必须退让"

    def test_overload_signal_retreats_without_waiting_window(self) -> None:
        limiter = self._limiter(max_limit=30, window=4)
        self._pump(limiter, 0.05, 4 * 8)  # 先爬到一定高度
        before = limiter.limit
        assert before >= 5

        # 单个过载信号就该立刻退让——不等攒满一个窗口的延迟样本
        limiter.release(latency=0.05, overload=True)

        assert limiter.limit == before - 2

    def test_never_exceeds_max_or_goes_below_one(self) -> None:
        limiter = self._limiter(max_limit=3, window=2, min_limit=1)
        self._pump(limiter, 0.01, 50)
        assert limiter.limit == 3
        for _ in range(50):
            limiter.release(latency=9.0, overload=True)
        assert limiter.limit == 1

    def test_acquire_blocks_until_release_then_succeeds(self) -> None:
        limiter = self._limiter(max_limit=1, window=4)
        assert limiter.acquire(timeout=0.1) is True  # 第一个槽位
        assert limiter.acquire(timeout=0.05) is False  # 上限 1，第二个拿不到

        threading.Timer(0.05, lambda: limiter.release(latency=0.01)).start()
        assert limiter.acquire(timeout=1.0) is True  # 释放后立刻能拿到

    def test_app_limited_does_not_raise_limit(self) -> None:
        """低流量样本里没有排队信息 → 不许上调（否则闲时爬满、忙时被打回，来回锯齿）。

        对照 Netflix Gradient2 的 `inflight < limit/2` 守卫。
        """
        limiter = self._limiter(max_limit=30, initial=10, window=4)

        for _ in range(200):
            # 只占 1 个槽位（远低于 10/2）就释放：延迟再漂亮也不能涨价
            assert limiter.acquire(timeout=0.05)
            limiter.release(latency=0.01)

        assert limiter.limit == 10, "app-limited 时不该上调 limit"


class TestFirmScheduling:
    """服务层把调度器接上：峰值不越过硬上限、过载后自动退让。"""

    @staticmethod
    def _cfg(module: Any, keys: int = 10, per_key: int = 3) -> Any:
        return module.FirmSearchConfig(
            url="http://gw/WebSearch/mcp",
            keys=tuple(f"sk-{i}" for i in range(keys)),
            timeout=5,
            provider="test",
            concurrency_per_key=per_key,
        )

    def _reset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        monkeypatch.setattr(module, "_limiter", None)
        monkeypatch.delenv(module.ENV_MAX_CONCURRENT, raising=False)

    def test_capacity_is_keys_times_per_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        self._reset(monkeypatch)
        limiter = module._limiter_for(self._cfg(module))
        assert limiter.max_limit == 30  # 10 把 key × 每把 3 并发

    def test_env_can_cap_below_hardware_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        self._reset(monkeypatch)
        monkeypatch.setenv(module.ENV_MAX_CONCURRENT, "4")
        limiter = module._limiter_for(self._cfg(module))
        assert limiter.max_limit == 4  # 所里想给检索留几个槽位

    def test_peak_never_exceeds_capacity_and_all_succeed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _firm_module()
        self._reset(monkeypatch)
        cfg = self._cfg(module, keys=4, per_key=3)  # 硬上限 12
        state = {"inflight": 0, "peak": 0}
        lock = threading.Lock()

        def fake_call(url: str, key: str, query: str, count: int, timeout: float) -> Any:
            with lock:
                state["inflight"] += 1
                state["peak"] = max(state["peak"], state["inflight"])
            time.sleep(0.02)
            with lock:
                state["inflight"] -= 1
            payload = {"status": 0, "pages": [{"title": "T", "url": "https://a.gov.cn/x", "snippet": "s"}]}
            envelope = {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]},
            }
            return module._Fetched(status_code=200, text=f"data: {json.dumps(envelope, ensure_ascii=False)}\n\n")

        monkeypatch.setattr(module, "_call", fake_call)
        # 每 key 并发由共享 Key 池负责，这里把池上限拉到 3 以模拟真实配置
        monkeypatch.setattr(module, "_key_pool", lambda c: _WidePool(list(c.keys)))

        with ThreadPoolExecutor(max_workers=24) as pool:
            results = list(pool.map(lambda _: module.search("合同", 3, cfg), range(24)))

        assert all(r["ok"] for r in results), collections.Counter(r.get("reason") for r in results)
        assert state["peak"] <= 12, f"越过硬上限：峰值 {state['peak']}"


class _WidePool:
    """不限制并发/冷却的池替身（调度器用例只验调度器本身）。"""

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        self._i = 0

    def acquire(self, model: str = "") -> int:
        idx = self._i % len(self.keys)
        self._i += 1
        return idx

    def release(self, idx: int, *, success: bool, model: str = "") -> None:
        return None


class TestUrlNormalization:
    """结果去重：同一篇文章带不带跟踪参数都是同一篇（SearXNG/ddgs 同族做法）。"""

    def test_tracking_params_and_fragment_ignored(self) -> None:
        module = _module()
        base = "https://www.court.gov.cn/zixun/xiangqing/419382.html"

        assert module._url_key(base) == module._url_key(base + "?utm_source=sohu&spm=a1")
        assert module._url_key(base) == module._url_key(base + "#section-2")
        assert module._url_key(base) == module._url_key("http://court.gov.cn/zixun/xiangqing/419382.html")

    def test_meaningful_query_kept(self) -> None:
        module = _module()
        a = module._url_key("https://a.gov.cn/doc?entityid=1")
        b = module._url_key("https://a.gov.cn/doc?entityid=2")

        assert a != b, "不同的业务参数必须算两篇"

    def test_dedupe_keeps_richer_snippet(self) -> None:
        module = _module()
        results = [
            module._SearchResult(title="甲", url="https://a.gov.cn/x?utm_source=1", snippet="短"),
            module._SearchResult(title="甲", url="https://a.gov.cn/x", snippet="更长的一段摘要"),
            module._SearchResult(title="乙", url="https://a.gov.cn/y", snippet="另一篇"),
        ]

        kept = module._dedupe_results(results)

        assert len(kept) == 2
        assert kept[0].snippet == "更长的一段摘要"

    def test_desktop_results_are_deduped(self, fake_http: dict[str, Any]) -> None:
        module = _module()
        html = (
            "<html><body>"
            '<div class="vrwrap"><h3><a href="https://a.gov.cn/x?utm_source=t">甲</a></h3>'
            '<div class="space-txt">摘要甲</div></div>'
            '<div class="vrwrap"><h3><a href="https://a.gov.cn/x">甲（转载）</a></h3>'
            '<div class="space-txt">摘要甲更长一些</div></div>'
            "</body></html>"
        )
        fake_http["responses"] = [_response(html)]

        text = module._do_search("合同", 5)

        assert "找到 1 条搜索结果" in text, text[:400]
