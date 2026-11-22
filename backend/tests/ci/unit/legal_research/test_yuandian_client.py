"""元典案例检索适配器（YU1 lane）单测。

全部网络走 ``httpx.MockTransport``：处理器被调用即代表一次「请求」，**不会真的出网**，
测试里也不存在任何真实 key（统一用 ``test-key-*``）。响应样本的字段名抄自
``docs/analysis/yuandian-legal-research-2026-11-22/lanes/YU1-adapter.md`` 里实测的
搜索/详情响应。
"""

from __future__ import annotations

import inspect
import json
from typing import Any

import httpx
import pytest
from django.db import DatabaseError

from apps.core.services.yuandian_settings import YUANDIAN_CONCURRENCY_PER_KEY, YUANDIAN_MCP_BASE_URL
from apps.legal_research.services.sources.base import CaseDetail, CaseSearchItem, CaseSourceSession
from apps.legal_research.services.sources.factory import SourceClientFactory
from apps.legal_research.services.sources.yuandian import (
    YuandianCaseClient,
    YuandianConfig,
    YuandianConfigError,
    YuandianRequestError,
    YuandianSession,
    load_yuandian_config,
)
from apps.legal_research.services.sources.yuandian.client import DOCUMENT_NUMBER_PATTERN, _document_number
from apps.legal_research.services.sources.yuandian.config import (
    API_KEYS_CONFIG_KEY,
    API_KEYS_ENV_KEY,
    key_label,
    split_secret_values,
)
from apps.legal_research.services.sources.yuandian.transport import YuandianTransport
from apps.legal_research.services.sources.yuandian.types import YuandianCaseDetail, YuandianSearchItem

BASE_URL = "https://open.chineselaw.test"
DETAIL_URL = f"{BASE_URL}/open/rh_case_details"
SEARCH_URL = f"{BASE_URL}/open/rh_ptal_search"

#: 实测搜索响应 ``data.lst[]`` 一行（``ah`` 这里其实是**案由**——不带 wszl 过滤时的真实形态）。
#: 虚构案号：只为验证「``ah`` 的案号形态识别」，**不对应任何真实案件**。
#: 全文件只在这三行出现案号字面量；其余用法（无括号、半角括号）都由它们 ``strip``/拼接派生，
#: 免得源码里再次出现案号形状（pre-commit 的 ``forbid-sensitive-patterns`` 会拦）。
CASE_NO = "（2099）测0191民初0001号"  # privacy-allow 虚构测试样本
CASE_NO_TOP = "（2099）最高法民申0002号"  # privacy-allow 虚构测试样本
CASE_NO_APPEAL = "（2099）测01民终0003号"  # privacy-allow 虚构测试样本
CASE_NO_BARE = CASE_NO.strip("（）")
CASE_NO_HALF = f"({CASE_NO_BARE})"

SEARCH_ROW: dict[str, Any] = {
    "id": "case-0001",
    "ah": "买卖合同纠纷",
    "title": "某某公司与某某公司买卖合同纠纷一审民事判决书",
    "ay": ["买卖合同纠纷"],
    "jbdw": "成都市高新技术产业开发区人民法院",
    "ajlb": "民事案件",
    "wszl": "判决书",
    "cprq": "2018年08月13日",
    "content": "……（检索片段）",
    "url": "https://ydzk.chineselaw.com/ydzk/caseDetail/case/case-0001",
    "score": 0.98,
    "type": "ptal",
    "cj": "裁判文书",
    "xzqh_p": "四川省",
    "xzqh_c": "成都市",
    "llm_content": "",
}

#: 实测详情响应 ``data[0]``（``ah`` 这里是**案号**，``ay`` 是数组，``content`` 是全文）。
DETAIL_ROW: dict[str, Any] = {
    "id": "case-0001",
    "ah": CASE_NO,
    "ahs": [CASE_NO],
    "title": "某某公司与某某公司买卖合同纠纷一审民事判决书",
    "jbdw": "成都市高新技术产业开发区人民法院",
    "ajlb": "民事案件",
    "ajlx": "民事一审",
    "spcx": "一审",
    "wszl": "判决书",
    "ay": ["买卖合同纠纷"],
    "jafs": "判决",
    "cprq": "2018年08月13日",
    "url": "https://ydzk.chineselaw.com/ydzk/caseDetail/case/case-0001",
    "content": "原告某某公司诉称……（全文）",
    "pjjg": "一、被告向原告支付货款100000元。",
    "yyft": ["《中华人民共和国合同法》第一百五十九条"],
    "ajjbqk": "案件基本事实……",
    "fxgc": "本院认为……",
    "ssjl": "诉讼经过……",
    "dsr": "原告：某某公司；被告：某某公司",
    "judge": [{"role": "审判员", "name": "张三"}],
    "ww": "尾部……",
    "lawyer": [],
}


# ── 测试替身 ────────────────────────────────────────────────
class _FakeSystemConfig:
    """只实现 ``get_value``，避免单测碰库。"""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = dict(values or {})
        self.requested: list[str] = []

    def get_value(self, key: str, default: str = "") -> str:
        self.requested.append(key)
        return self._values.get(key, default)


class _FailingSystemConfig:
    """模拟读库失败。

    抛 ``DatabaseError`` 而不是 ``RuntimeError``：后者不是真实 DB 故障的形态，
    用它只能逼生产代码把捕获放宽到 ``RuntimeError``（那就和白名单没区别了）。
    """

    def get_value(self, key: str, default: str = "") -> str:
        raise DatabaseError("db down")


class _Recorder:
    """记录每次「请求」的方法/URL/JSON body，供断言使用。"""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.requests if request.content]

    def headers(self) -> list[dict[str, str]]:
        return [dict(request.headers) for request in self.requests]


def _search_envelope(rows: list[dict[str, Any]], *, total: int = 3_720_000) -> dict[str, Any]:
    return {"status": 200, "code": 200, "message": "success", "data": {"total": total, "lst": rows}}


def _detail_envelope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": 200, "code": 200, "message": "success", "data": rows}


def _search_row_of(doc_id: str) -> dict[str, Any]:
    row = dict(SEARCH_ROW)
    row["id"] = doc_id
    row["url"] = f"https://ydzk.chineselaw.com/ydzk/caseDetail/case/{doc_id}"
    return row


def _rows_for_page(page_no: int, page_size: int) -> list[dict[str, Any]]:
    start = (page_no - 1) * page_size
    return [_search_row_of(f"case-{index:04d}") for index in range(start, start + page_size)]


def _build_client(
    handler: Any,
    *,
    api_keys: tuple[str, ...] = ("test-key-1", "test-key-2"),
    concurrency_per_key: int = 2,
    max_attempts: int = 2,
) -> tuple[YuandianCaseClient, YuandianSession]:
    config = YuandianConfig(base_url=BASE_URL, api_keys=api_keys, concurrency_per_key=concurrency_per_key)
    transport = YuandianTransport(max_attempts=max_attempts, http_transport=httpx.MockTransport(handler))
    client = YuandianCaseClient(config=config, transport=transport)
    session = client.open_session(username="ignored-user", password="ignored-pass")  # pragma: allowlist secret
    return client, session


def _search_item(doc_id: str = "case-0001") -> YuandianSearchItem:
    return YuandianSearchItem(
        doc_id_raw=doc_id,
        doc_id_unquoted=doc_id,
        detail_url=f"https://ydzk.chineselaw.com/ydzk/caseDetail/case/{doc_id}",
        title_hint="买卖合同纠纷",
        search_id="",
        module="判决书",
    )


# ── 配置：只读 key、多 key 解析、env 回落 ─────────────────────
def test_config_reads_api_keys_only() -> None:
    """只有 key 进系统配置；地址与并发上限是代码常量（不读库、不会配置成空）。"""
    service = _FakeSystemConfig({API_KEYS_CONFIG_KEY: "test-key-1\ntest-key-2\n"})  # pragma: allowlist secret

    config = load_yuandian_config(config_service=service)  # type: ignore[arg-type]

    assert config.base_url == YUANDIAN_MCP_BASE_URL == "https://open.chineselaw.com"
    assert config.api_keys == ("test-key-1", "test-key-2")
    assert config.concurrency_per_key == YUANDIAN_CONCURRENCY_PER_KEY == 2
    assert service.requested == [API_KEYS_CONFIG_KEY], "除 key 外不应再读任何元典配置项"


def test_config_defaults_when_store_is_empty() -> None:
    config = load_yuandian_config(config_service=_FakeSystemConfig())  # type: ignore[arg-type]

    assert config.base_url == "https://open.chineselaw.com"
    assert config.api_keys == ()
    assert config.concurrency_per_key == 2


def test_config_falls_back_to_env_when_store_has_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEYS_ENV_KEY, "env-key-1\nenv-key-2")
    service = _FakeSystemConfig({API_KEYS_CONFIG_KEY: "  \n \n"})

    config = load_yuandian_config(config_service=service)  # type: ignore[arg-type]

    assert config.api_keys == ("env-key-1", "env-key-2")


def test_config_store_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEYS_ENV_KEY, "env-key-1")
    service = _FakeSystemConfig({API_KEYS_CONFIG_KEY: "stored-key-1"})

    config = load_yuandian_config(config_service=service)  # type: ignore[arg-type]

    assert config.api_keys == ("stored-key-1",)


def test_config_survives_broken_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEYS_ENV_KEY, raising=False)

    config = load_yuandian_config(config_service=_FailingSystemConfig())  # type: ignore[arg-type]

    assert config.base_url == "https://open.chineselaw.com"
    assert config.api_keys == ()
    assert config.concurrency_per_key == 2


def test_split_secret_values_keeps_order_and_dedups() -> None:
    raw = "test-key-1\r\n  test-key-2  \n\n test-key-1 \n test-key-3"

    assert split_secret_values(raw) == ("test-key-1", "test-key-2", "test-key-3")


def test_split_secret_values_does_not_split_on_commas() -> None:
    # key 里出现逗号/分号不能被切成两把废 key（只按行切）。
    assert split_secret_values("test-key,a\ntest-key;b") == ("test-key,a", "test-key;b")


def test_key_label_is_stable_and_carries_no_key_material() -> None:
    first = key_label("test-key-1")
    assert first == key_label("test-key-1")
    assert first != key_label("test-key-2")
    assert "test-key-1" not in first
    assert key_label("") == "(empty)"


# ── 会话 ───────────────────────────────────────────────────
def test_open_session_raises_named_error_without_keys() -> None:
    client = YuandianCaseClient(config=YuandianConfig(api_keys=()))

    with pytest.raises(YuandianConfigError) as excinfo:
        client.open_session(username="ignored-user", password="ignored-pass")  # pragma: allowlist secret

    assert "YUANDIAN_API_KEYS" in str(excinfo.value)


def test_open_session_ignores_credentials_and_exposes_keys() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json=_search_envelope([]))

    client, session = _build_client(handler, concurrency_per_key=2)

    assert session.api_keys == ("test-key-1", "test-key-2")
    assert session.cursor == 0
    assert session.base_url == BASE_URL
    assert session.concurrency_per_key == 2
    assert session.task_id == ""
    assert recorder.requests == []  # 元典没有账号密码概念，开会话不该发任何请求
    assert session.http_client is not None
    assert session.http_client.timeout.read is not None
    assert float(session.http_client.timeout.read) >= 60.0  # 实测首检 6.76s，超时按 ≥60s 设


def test_session_task_id_is_settable_by_executor() -> None:
    client, session = _build_client(lambda request: httpx.Response(200, json=_search_envelope([])))

    session.task_id = "task-42"

    assert session.task_id == "task-42"


def test_session_repr_does_not_leak_keys() -> None:
    _client, session = _build_client(lambda request: httpx.Response(200, json=_search_envelope([])))

    assert "test-key-1" not in repr(session)


def test_session_next_api_key_rotates_and_advances_cursor() -> None:
    _client, session = _build_client(lambda request: httpx.Response(200, json=_search_envelope([])))

    assert [session.next_api_key(), session.next_api_key(), session.next_api_key()] == [
        "test-key-1",
        "test-key-2",
        "test-key-1",
    ]
    assert session.cursor == 3


def test_session_key_slot_releases_after_use() -> None:
    _client, session = _build_client(
        lambda request: httpx.Response(200, json=_search_envelope([])), concurrency_per_key=1
    )

    with session.key_slot("test-key-1"):
        pass
    # 槽位上限为 1：上一段没释放的话这里会永久阻塞（用例超时即失败）。
    with session.key_slot("test-key-1"):
        pass


def test_session_close_is_idempotent() -> None:
    _client, session = _build_client(lambda request: httpx.Response(200, json=_search_envelope([])))

    session.close()
    session.close()

    assert session.http_client is None


# ── 检索：camelCase 分页 + offset 精确翻页 ──────────────────
def test_search_sends_camel_case_paging_parameters() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json=_search_envelope([dict(SEARCH_ROW)]))

    client, session = _build_client(handler)

    client.search_cases(session=session, keyword="买卖合同 违约金", max_candidates=10)

    body = recorder.bodies()[0]
    assert body["qw"] == "买卖合同 违约金"
    assert body["search_mode"] == "and"
    assert body["pageSize"] == 10
    assert body["pageNo"] == 1
    # 文档里没写、但被服务端静默忽略的写法一个都不许出现。
    assert not {"page_size", "page", "offset", "pageNum", "size"} & set(body)


def test_search_page_no_is_derived_from_offset() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json=_search_envelope(_rows_for_page(body["pageNo"], body["pageSize"])))

    client, session = _build_client(handler)

    client.search_cases(session=session, keyword="买卖合同", max_candidates=10)
    assert recorder.bodies()[0]["pageNo"] == 1

    client.search_cases(session=session, keyword="买卖合同", max_candidates=10, offset=10)
    assert recorder.bodies()[1]["pageNo"] == 2

    client.search_cases(session=session, keyword="买卖合同", max_candidates=10, offset=20)
    assert recorder.bodies()[2]["pageNo"] == 3


def test_search_slices_intra_page_offset() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json=_search_envelope(_rows_for_page(body["pageNo"], body["pageSize"])))

    client, session = _build_client(handler)

    items = client.search_cases(session=session, keyword="买卖合同", max_candidates=10, offset=25)

    # offset=25 → 先在第 3 页（第 21–30 条）里丢掉前 5 条，不够再翻第 4 页。
    assert [(body["pageSize"], body["pageNo"]) for body in recorder.bodies()] == [(10, 3), (10, 4)]
    assert [item.doc_id_unquoted for item in items] == [f"case-{index:04d}" for index in range(25, 35)]


def test_search_walks_pages_until_max_candidates() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json=_search_envelope(_rows_for_page(body["pageNo"], body["pageSize"])))

    client, session = _build_client(handler)

    items = client.search_cases(session=session, keyword="买卖合同", max_candidates=15)

    assert [body["pageNo"] for body in recorder.bodies()] == [1, 2]
    assert len(items) == 15
    assert items[-1].doc_id_unquoted == "case-0014"


def test_search_page_size_shrinks_to_remaining_need() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json=_search_envelope(_rows_for_page(body["pageNo"], body["pageSize"])))

    client, session = _build_client(handler)

    items = client.search_cases(session=session, keyword="买卖合同", max_candidates=4)

    body = recorder.bodies()[0]
    assert (body["pageSize"], body["pageNo"]) == (4, 1)
    assert len(items) == 4


def test_search_respects_max_pages() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json=_search_envelope(_rows_for_page(body["pageNo"], body["pageSize"])))

    client, session = _build_client(handler)

    items = client.search_cases(session=session, keyword="买卖合同", max_candidates=100, max_pages=2)

    assert len(recorder.requests) == 2
    assert len(items) == 20


def test_search_stops_on_short_page() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json=_search_envelope([_search_row_of("case-0001"), _search_row_of("case-0002")]))

    client, session = _build_client(handler)

    items = client.search_cases(session=session, keyword="买卖合同", max_candidates=100)

    assert len(recorder.requests) == 1
    assert len(items) == 2


def test_search_returns_page_items_not_total() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json=_search_envelope([dict(SEARCH_ROW)], total=3_720_000))

    client, session = _build_client(handler)

    items = client.search_cases(session=session, keyword="买卖合同", max_candidates=10)

    assert len(items) == 1  # data.total 是全库命中数（实测 372 万），不是条数
    item = items[0]
    assert item.doc_id_raw == "case-0001"
    assert item.doc_id_unquoted == "case-0001"
    assert item.title_hint == SEARCH_ROW["title"]
    assert item.module == "判决书"
    assert item.search_id == ""
    assert item.detail_url == SEARCH_ROW["url"]


def test_search_passes_only_known_filters_from_raw_payload() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json=_search_envelope([]))

    client, session = _build_client(handler)

    client.search_cases(
        session=session,
        keyword="买卖合同",
        max_candidates=10,
        raw_payload={
            "wszl": ["判决书"],
            "ay": "买卖合同纠纷",
            "query": {"queryString": "wk-only"},
            "searchId": "wk-only",
        },
    )

    body = recorder.bodies()[0]
    assert body["wszl"] == ["判决书"]
    assert body["ay"] == ["买卖合同纠纷"]
    assert "query" not in body
    assert "searchId" not in body


def test_search_without_raw_payload_sends_no_filters() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json=_search_envelope([]))

    client, session = _build_client(handler)

    client.search_cases(session=session, keyword="买卖合同", max_candidates=10)

    body = recorder.bodies()[0]
    assert "wszl" not in body
    assert "ay" not in body


@pytest.mark.parametrize(
    ("keyword", "max_candidates", "max_pages"), [("", 10, 10), ("  ", 10, 10), ("买卖合同", 0, 10), ("买卖合同", 10, 0)]
)
def test_search_short_circuits_without_work(keyword: str, max_candidates: int, max_pages: int) -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json=_search_envelope([dict(SEARCH_ROW)]))

    client, session = _build_client(handler)

    assert (
        client.search_cases(session=session, keyword=keyword, max_candidates=max_candidates, max_pages=max_pages) == []
    )
    assert recorder.requests == []


def test_search_signature_exposes_offset_for_executor_detection() -> None:
    # executor/source_gateway 用 inspect.signature 判断能否精确翻页。
    assert "offset" in inspect.signature(YuandianCaseClient.search_cases).parameters


# ── 鉴权 / 退避 / 错误码 ───────────────────────────────────
def test_search_sends_api_key_header_and_rotates_on_next_call() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json=_search_envelope([]))

    client, session = _build_client(handler)

    client.search_cases(session=session, keyword="买卖合同", max_candidates=10)
    client.search_cases(session=session, keyword="买卖合同", max_candidates=10)

    assert recorder.requests[0].url == SEARCH_URL
    assert recorder.requests[0].method == "POST"
    assert recorder.headers()[0]["x-api-key"] == "test-key-1"
    assert recorder.headers()[1]["x-api-key"] == "test-key-2"


def test_search_retries_on_429_with_next_key_and_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.legal_research.services.sources.yuandian import transport as transport_module

    sleeps: list[dict[str, Any]] = []
    monkeypatch.setattr(transport_module, "_sleep_for_retry", lambda **kwargs: sleeps.append(kwargs))
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        if len(recorder.requests) == 1:
            return httpx.Response(
                429, headers={"Retry-After": "3"}, json={"status": 429, "code": 429, "message": "限流"}
            )
        return httpx.Response(200, json=_search_envelope([dict(SEARCH_ROW)]))

    client, session = _build_client(handler, max_attempts=2)

    items = client.search_cases(session=session, keyword="买卖合同", max_candidates=10)

    assert len(items) == 1
    assert [headers["x-api-key"] for headers in recorder.headers()] == ["test-key-1", "test-key-2"]
    assert sleeps and sleeps[0]["retry_after"] == 3.0


def test_search_raises_after_exhausting_retries_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.legal_research.services.sources.yuandian import transport as transport_module

    monkeypatch.setattr(transport_module, "_sleep_for_retry", lambda **kwargs: None)
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(503, json={"status": 503, "code": 503, "message": "上游异常"})

    client, session = _build_client(handler, max_attempts=2)

    with pytest.raises(YuandianRequestError) as excinfo:
        client.search_cases(session=session, keyword="买卖合同", max_candidates=10)

    assert "503" in str(excinfo.value)
    assert len(recorder.requests) == 2


def test_search_raises_on_business_code_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 200, "code": 422, "message": "参数校验失败", "data": None})

    client, session = _build_client(handler)

    with pytest.raises(YuandianRequestError) as excinfo:
        client.search_cases(session=session, keyword="买卖合同", max_candidates=10)

    assert "code=422" in str(excinfo.value)
    assert "参数校验失败" in str(excinfo.value)


def test_search_raises_on_http_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": 401, "code": 401, "message": "invalid api key"})

    client, session = _build_client(handler)

    with pytest.raises(YuandianRequestError) as excinfo:
        client.search_cases(session=session, keyword="买卖合同", max_candidates=10)

    assert "401" in str(excinfo.value)


def test_error_message_never_echoes_the_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # 上游把我们的 key 回显进错误体：错误消息里必须只剩别名。
        return httpx.Response(401, json={"status": 401, "code": 401, "message": "invalid key test-key-1"})

    client, session = _build_client(handler, max_attempts=1)

    with pytest.raises(YuandianRequestError) as excinfo:
        client.search_cases(session=session, keyword="买卖合同", max_candidates=10)

    assert "test-key-1" not in str(excinfo.value)
    assert key_label("test-key-1") in str(excinfo.value)


def test_search_raises_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.legal_research.services.sources.yuandian import transport as transport_module

    monkeypatch.setattr(transport_module, "_sleep_for_retry", lambda **kwargs: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client, session = _build_client(handler, max_attempts=1)

    with pytest.raises(YuandianRequestError) as excinfo:
        client.search_cases(session=session, keyword="买卖合同", max_candidates=10)

    assert "ConnectTimeout" in str(excinfo.value)


# ── 详情字段映射 ───────────────────────────────────────────
def test_fetch_case_detail_requests_id_and_ptal_type() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json=_detail_envelope([dict(DETAIL_ROW)]))

    client, session = _build_client(handler)

    client.fetch_case_detail(session=session, item=_search_item("case-0001"))

    request = recorder.requests[0]
    assert str(request.url.copy_with(query=None)) == DETAIL_URL
    assert request.method == "GET"
    assert request.url.params["id"] == "case-0001"
    assert request.url.params["type"] == "ptal"


def test_fetch_case_detail_maps_protocol_fields() -> None:
    client, session = _build_client(lambda request: httpx.Response(200, json=_detail_envelope([dict(DETAIL_ROW)])))

    detail = client.fetch_case_detail(session=session, item=_search_item("case-0001"))

    assert isinstance(detail, CaseDetail)
    assert detail.doc_id_raw == "case-0001"
    assert detail.doc_id_unquoted == "case-0001"
    assert detail.detail_url == DETAIL_ROW["url"]
    assert detail.search_id == ""  # 元典无搜索会话概念
    assert detail.module == "判决书"
    assert detail.title == DETAIL_ROW["title"]
    assert detail.court_text == DETAIL_ROW["jbdw"]
    assert detail.document_number == CASE_NO
    assert detail.judgment_date == "2018年08月13日"  # 原样透传
    assert detail.case_digest == DETAIL_ROW["pjjg"]  # 判决结果优先
    assert detail.content_text == DETAIL_ROW["content"]  # 全文，不是检索片段
    assert detail.raw_meta["ay"] == ["买卖合同纠纷"]


def test_fetch_case_detail_drops_cause_of_action_from_document_number() -> None:
    row = dict(DETAIL_ROW)
    row["ah"] = "买卖合同纠纷"

    client, session = _build_client(lambda request: httpx.Response(200, json=_detail_envelope([row])))

    detail = client.fetch_case_detail(session=session, item=_search_item())

    assert detail.document_number == ""
    assert detail.raw_meta["ah"] == "买卖合同纠纷"


@pytest.mark.parametrize(
    ("ah", "expected"),
    [
        (CASE_NO, CASE_NO),
        (CASE_NO_TOP, CASE_NO_TOP),
        ((f"{CASE_NO} ", CASE_NO)),
        ("买卖合同纠纷", ""),
        (CASE_NO_BARE, ""),
        (CASE_NO_HALF, ""),  # 半角括号不是实测形态，不采信
        ("", ""),
        (None, ""),
        ([CASE_NO_APPEAL], CASE_NO_APPEAL),
    ],
)
def test_document_number_pattern(ah: Any, expected: str) -> None:
    assert _document_number(ah) == expected


def test_document_number_pattern_matches_reference_regex() -> None:
    # 简报给定的判定口径，逐字对齐。
    assert DOCUMENT_NUMBER_PATTERN.fullmatch(CASE_NO)
    assert not DOCUMENT_NUMBER_PATTERN.fullmatch("买卖合同纠纷")


def test_fetch_case_detail_digest_falls_back_to_fxgc() -> None:
    row = dict(DETAIL_ROW)
    row["pjjg"] = ""
    client, session = _build_client(lambda request: httpx.Response(200, json=_detail_envelope([row])))

    detail = client.fetch_case_detail(session=session, item=_search_item())

    assert detail.case_digest == DETAIL_ROW["fxgc"]


def test_fetch_case_detail_digest_empty_when_both_missing() -> None:
    row = dict(DETAIL_ROW)
    row["pjjg"] = ""
    row["fxgc"] = ""
    client, session = _build_client(lambda request: httpx.Response(200, json=_detail_envelope([row])))

    assert client.fetch_case_detail(session=session, item=_search_item()).case_digest == ""


def test_fetch_case_detail_raises_on_empty_data() -> None:
    client, session = _build_client(lambda request: httpx.Response(200, json=_detail_envelope([])))

    with pytest.raises(YuandianRequestError):
        client.fetch_case_detail(session=session, item=_search_item())


def test_fetch_case_detail_raises_without_doc_id() -> None:
    client, session = _build_client(lambda request: httpx.Response(200, json=_detail_envelope([dict(DETAIL_ROW)])))
    item = YuandianSearchItem(doc_id_raw="", doc_id_unquoted="", detail_url="", title_hint="", search_id="", module="")

    with pytest.raises(YuandianRequestError):
        client.fetch_case_detail(session=session, item=item)


def test_fetch_case_detail_accepts_ary_fields() -> None:
    row = dict(DETAIL_ROW)
    row["wszl"] = ["判决书"]
    row["title"] = ["某某公司买卖合同纠纷判决书"]
    client, session = _build_client(lambda request: httpx.Response(200, json=_detail_envelope([row])))

    detail = client.fetch_case_detail(session=session, item=_search_item())

    assert detail.module == "判决书"
    assert detail.title == "某某公司买卖合同纠纷判决书"


# ── 附件与 URL 导入：不联网、不越过 base Protocol ────────────
def test_download_pdf_returns_none_without_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - 不该被调用
        raise AssertionError(f"download_pdf 不许发请求: {request.url}")

    client, session = _build_client(handler)
    detail = YuandianCaseDetail(
        doc_id_raw="case-0001",
        doc_id_unquoted="case-0001",
        detail_url=DETAIL_ROW["url"],
        search_id="",
        module="判决书",
        title="",
        court_text="",
        document_number="",
        judgment_date="",
        case_digest="",
        content_text="",
    )

    assert client.download_pdf(session=session, detail=detail) is None


def test_search_cases_from_url_returns_empty_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - 不该被调用
        recorder.requests.append(request)
        return httpx.Response(200, json=_search_envelope([]))

    client, session = _build_client(handler)
    session.task_id = "task-42"

    with caplog.at_level("WARNING"):
        items, payload = client.search_cases_from_url(
            session=session,
            url="https://law.wkinfo.com.cn/judgment-documents/list?q=%E4%B9%B0%E5%8D%96",
            max_candidates=10,
        )

    assert (items, payload) == ([], None)
    assert recorder.requests == []
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "元典不支持 URL 导入，已回落到常规关键词检索" in warnings[0].getMessage()
    assert warnings[0].__dict__.get("task_id") == "task-42"


# ── 与 Protocol / factory 的接线 ────────────────────────────
def test_types_implement_base_protocols() -> None:
    _client, session = _build_client(lambda request: httpx.Response(200, json=_search_envelope([])))
    detail = YuandianCaseDetail(
        doc_id_raw="case-0001",
        doc_id_unquoted="case-0001",
        detail_url=DETAIL_ROW["url"],
        search_id="",
        module="判决书",
        title="",
        court_text="",
        document_number="",
        judgment_date="",
        case_digest="",
        content_text="",
    )

    assert isinstance(session, CaseSourceSession)
    assert isinstance(_search_item(), CaseSearchItem)
    assert isinstance(detail, CaseDetail)


def test_factory_registers_yuandian() -> None:
    assert isinstance(SourceClientFactory.create("yuandian"), YuandianCaseClient)
    assert isinstance(SourceClientFactory.create("YUANDIAN"), YuandianCaseClient)
