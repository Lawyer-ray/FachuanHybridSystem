"""压缩上下文也参与轮次级 key 分配。

## 为什么压缩要单独测

压缩与正常对话打的是**同一批网关 key**（每把限 3 并发）。若压缩还走后端自己的
``_next_key``，它可能正好压在某个已有 3 个对话在用的 key 上 → 429 → 用户看到
「压缩卡住 60 秒」。而那一刻往往正是他上下文快爆了、最需要压缩成功的时候。

三个性质必须钉住：
1. 压缩**真的把分配到的 key 传给了 pi 进程**（传了但没到 pool = 白分配）；
2. 用完**归还**（漏归还 = 永久占掉一个并发槽，之后越来越容易 429）；
3. 拿不到 key 池时传 ``None``（回落后端轮转，不能报错——压缩不该因运维配错而失败）。
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from apps.agent.backends.key_scheduler import get_key_scheduler
from apps.agent.services import compact_service


class _FakePiSession:
    async def compact(self) -> None:
        return None

    async def get_session_stats(self) -> dict[str, Any]:
        return {"contextUsage": {"tokens": 10, "contextWindow": 100}}


class _FakePool:
    """记录 ``acquire`` 收到的 ``api_key``，并模拟一个可用的 pi 会话。"""

    def __init__(self, *, fail: BaseException | None = None) -> None:
        self.received_keys: list[str | None] = []
        self.fail = fail

    def acquire(self, **kwargs: Any) -> Any:
        self.received_keys.append(kwargs.get("api_key"))

        @contextlib.asynccontextmanager
        async def _cm() -> Any:
            if self.fail is not None:
                raise self.fail
            yield _FakePiSession()

        return _cm()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    """把「查会话 / 铸 token / 起池 / 落库」全部打桩，只留 key 分配是真的。"""
    get_key_scheduler().reset()

    async def _token(_uid: int | None) -> str:
        return "tool-token"

    def _env(*_a: Any, **_kw: Any) -> dict[str, str]:
        return {}

    async def _noop_create(**_kw: Any) -> None:
        return None

    # has_pi_session 经 sync_to_async 包一层调用，所以桩本身必须是**同步**函数。
    monkeypatch.setattr(compact_service, "has_pi_session", lambda _sid: True)
    monkeypatch.setattr(compact_service.env, "mint_user_token", _token)
    monkeypatch.setattr(compact_service.env, "session_env", _env)
    monkeypatch.setattr(compact_service, "AgentMessage", _FakeMessage)


class _FakeMessage:
    class Role:
        TOOL = "tool"

    @staticmethod
    async def acreate(**_kw: Any) -> None:
        return None


async def _run(pool: _FakePool, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    async def _get_pool() -> _FakePool:
        return pool

    monkeypatch.setattr(compact_service, "get_pool", _get_pool)
    return await compact_service.compact_session(session=_Session(), user_id=1)  # type: ignore[arg-type]


class _Session:
    """足够 ``compact_session`` 用的会话桩（它只读 ``llm_model`` 与 session_id）。"""

    session_id = "11111111-1111-1111-1111-111111111111"
    llm_model = "kimi-2.6"


@pytest.mark.asyncio
async def test_compaction_passes_allocated_key_to_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """分配到的 key 必须真的传到 ``pool.acquire``。

    只断言「调度器返回了一把 key」是不够的——那证明不了它到了 pi 进程。
    四层里任何一层漏传，表现都是「压缩偶尔卡 60 秒」，没有报错。
    """
    keys = ("sk-A", "sk-B", "sk-C")

    async def _load(_model_hint: str | None) -> tuple[str, ...]:
        return keys

    monkeypatch.setattr(compact_service, "load_api_keys", _load)
    pool = _FakePool()
    await _run(pool, monkeypatch)

    assert len(pool.received_keys) == 1
    assert pool.received_keys[0] in keys, f"压缩没拿到池里的 key：{pool.received_keys}"


@pytest.mark.asyncio
async def test_compaction_releases_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    """压缩结束必须归还租约，否则这把 key 的并发槽被永久占掉。"""

    async def _load(_model_hint: str | None) -> tuple[str, ...]:
        return ("sk-A",)

    monkeypatch.setattr(compact_service, "load_api_keys", _load)
    await _run(_FakePool(), monkeypatch)

    assert get_key_scheduler().snapshot() == {}, "压缩结束后租约没归还"


@pytest.mark.asyncio
async def test_compaction_releases_lease_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """pi 进程起不来时也要归还——异常路径最容易漏，漏一次槽位就少一个。"""

    async def _load(_model_hint: str | None) -> tuple[str, ...]:
        return ("sk-A",)

    monkeypatch.setattr(compact_service, "load_api_keys", _load)
    with pytest.raises(RuntimeError):
        await _run(_FakePool(fail=RuntimeError("pi 挂了")), monkeypatch)

    assert get_key_scheduler().snapshot() == {}, "异常路径漏了归还"


@pytest.mark.asyncio
async def test_compaction_without_keys_passes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """拿不到 key 池时传 ``None``（回落后端轮转），**不能报错**。

    压缩是用户在上下文快爆时主动点的动作，不该因为运维把 provider 配坏而失败。
    """

    async def _load(_model_hint: str | None) -> tuple[str, ...]:
        return ()

    monkeypatch.setattr(compact_service, "load_api_keys", _load)
    pool = _FakePool()
    await _run(pool, monkeypatch)

    assert pool.received_keys == [None], "无 key 池时不该传空串（后端会当成一把空 key）"
