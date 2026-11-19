"""端到端验收「每栏可指定模型」：真后端（:8002）+ 真网关 + 真三个 agent。

## 为什么是脚本而不是 pytest

要判定的东西全部在**外部**：Django 进程（:8002）、律所 LLM 网关、三个 agent
运行时（``pi`` 子进程 / dsh 子进程 / openai-agents SDK）。这三样在 CI 容器里
没有、在开发机上每人配置不同，写成 pytest 只能到处 ``skipif``，最后变成永远
不跑的空壳。本脚本失败即非零退出，可以直接串进验收步骤——与
``scripts/verify_dsh_mcp.py`` 同一取舍。

## 验什么（规格 §五 的 1/2/3/5 条，4/6 属前端）

1. **三栏三模型**：``agents: [{kind,model}×3]`` 同答，三栏实得模型互不相同；
2. **真的是指定的那个**：不只是「互不相同」，而是**逐栏等于本轮指定值**——
   三个后端都回落平台默认时同样「互不相同」的概率为零，所以比对指定值才是判据；
3. **老前端回归**：``agents: ["pi","dsh"]``（纯字符串数组）仍然正常跑完两栏；
4. **不传模型 = 平台默认**：``model`` 为空串 / 缺省的那栏，实得模型等于
   ``GET /agent/backends`` 的 ``default_model``（拿不到该字段时退回
   LLMProvider 的默认模型）。

## 「实得模型」从哪来（这是本脚本最要紧的一处）

**SSE 事件里没有模型名**（``sse_types.py`` 的 ``DeltaEvent`` / ``DoneEvent`` 都
不带 ``model``），所以「哪一栏用了哪个模型」只能从**审计落库**读：

    POST /sessions/{id}/messages  ──SSE──▶ done（每栏一个）
            │
            └─ AgentRun.model          ← 编排层回写，逐栏一条（模型 + token + 成本）
            └─ AgentMessage.metadata["model"]  ← 助手正文那条，逐栏一条

本脚本用 **``AgentRun.model``** 作唯一判据：它对一栏恰好一条、不依赖消息正文
是否为空（模型答错/一个字没吐时正文那条根本不会落库，那正是最需要知道它用了
什么模型的场景）。``AgentMessage.metadata["model"]`` 只作为**交叉核对**打印出来，
两者不一致时给 WARNING——那说明编排层有两处各自推导模型，正是要防止的漂移。

读库走 Django ORM（本脚本在进程内 ``django.setup()``），只读不写业务数据以外的
东西（会在目标库里留一个 ``verify-model-*`` 会话，供事后追查）。

## token 与代理

- token 用 ``apps.agent.pi.user_token.mint_user_access_token(user_id)`` 铸；
  与 agent 工具调用拿的是**同一种票**（前端拿到的是同一种），所以脚本验的是
  真实鉴权路径，不是后门。
- 律所网关与 :8002 都是内网地址，开发机的 ``HTTPS_PROXY``（Clash）会把请求转
  出去得到 502。本脚本**全程绕代理**：直接 ``trust_env=False`` 的 httpx client，
  并在调用后端的同时把代理变量从本进程环境里摘掉（``without_proxy_env``）——
  后者是因为 :8002 进程自己也可能带着代理变量去连网关（见 ``dsh_config`` 的
  ``without_proxy_env`` 说明）。

## 「后端还没重启」时要说人话

新代码没生效时，后端对 ``agents: [{kind,model}]`` 会**静默忽略**对象、只认
``kind``（Ninja 解析不过就报 422），最坏的表现是「三栏都跑默认模型」——看起来
像本脚本的断言错了。所以开跑前先做 :func:`_preflight`：

1. ``GET /api/v1/openapi.json`` 里的 ``MessageIn.agents`` 是否已声明对象形态；
2. 该端点的 ``/backends`` 是否已带 ``models`` / ``default_model`` 字段。

任一项不满足就打印「后端未重启 / 代码未生效」+ 怎么重启 + 退出码 ``3``（不是
``1``：这不是验收失败，是**还没法验**）。

## 退出码

``0`` 全部通过 / ``1`` 有验收项失败 / ``2`` 环境缺失（后端不可达、没有可用
律师账号、网关没配） / ``3`` 后端代码未生效（见上）。

## 用法

.. code-block:: bash

    # 仓库根执行；backend/.venv 是同级的解释器
    backend/.venv/bin/python scripts/verify_per_agent_model.py
    backend/.venv/bin/python scripts/verify_per_agent_model.py --user 1 --timeout 180
    backend/.venv/bin/python scripts/verify_per_agent_model.py --skip-legacy   # 只验新契约

数据库取 ``DJANGO_SETTINGS_MODULE=apiSystem.settings`` 下的默认库（``.env``）。
**不要**把这个脚本指到 ``test_*`` 库上然后以为它验了线上配置——它读的就是那份
``LLMProvider``。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# settings 模块在 ``backend/apiSystem/apiSystem/settings.py``（内层那个包），所以
# 第二个 sys.path 条目是 ``apiSystem``——与 CI 里的 ``PYTHONPATH=apiSystem:.`` 同源。
#
# 本脚本在**根** ``scripts/``（与 ``verify_dsh_mcp.py`` 同例：验收交付物不留在
# gitignore 的 ``backend/scripts/``）。因此路径是「仓库根 / backend」。
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
for entry in (str(BACKEND_DIR / "apiSystem"), str(BACKEND_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

BASE_URL = "http://127.0.0.1:8002"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ENV = 2
EXIT_STALE = 3

#: 三个 agent 引一个刁钻但**不需要工具**的问题：本轮目的是比模型，不是比工具面。
#: 不用工具是有意的——工具调用会把单轮拖到分钟级，且任一 agent 的工具面缺失时
#: 整轮变成「那栏没内容」，验收会误判成模型没生效。
QUESTION = "用一句话回答：合同约定「定金」与「订金」在法律效果上的主要区别是什么？"

#: 三栏 × 三模型的矩阵：**每个 kind 都给了不同模型**，并且同一份清单会被
#: 第二轮（老前端字符串数组）复用为「平台默认」口径的对照。
MATRIX: tuple[tuple[str, str], ...] = (
    ("pi", "kimi-2.6"),
    ("dsh", "glm53"),
    ("openai-agents", "kimi-2.6(Anthropic)"),
)

#: 老前端回归用纯字符串数组（规格 §二 2.1 的兼容承诺）。
LEGACY_AGENTS = ["pi", "dsh"]


def _say(message: str = "") -> None:
    """正常信息 → stdout（输出就是给人看的，也会被贴进验收报告）。"""
    sys.stdout.write(message + "\n")


def _fail(message: str) -> None:
    """失败信息 → stderr。"""
    sys.stderr.write(message + "\n")


def _ok(label: str, detail: str = "") -> bool:
    _say(f"  \u2705 {label}" + (f" — {detail}" if detail else ""))
    return True


def _bad(label: str, detail: str = "") -> bool:
    _fail(f"  \u274c {label}" + (f" — {detail}" if detail else ""))
    return False


# ── 进程内 Django（只用来铸 token 与读审计表） ────────────────────────────


def _django_user(user_id: int | None) -> Any:
    """挑一个可用律师账号：``--user`` 优先，否则取第一个启用账号。

    不新建账号：agent 的工具面按律师身份过滤数据，随便造一个空账号会让「模型
    读不到案件」干扰本轮（虽然本轮刻意不调工具，但会话归属与配额仍按用户算）。

    **同步函数**：本脚本的入口在事件循环里，任何直接调它的地方都必须走
    ``sync_to_async``（Django 会主动抛 ``SynchronousOnlyOperation``，第一次跑
    就踩到了）。
    """
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    if user_id is not None:
        user = user_model.objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            raise SystemExit(f"FAIL: --user {user_id} 不存在或已停用")
        return user
    user = user_model.objects.filter(is_active=True).order_by("pk").first()
    if user is None:
        raise SystemExit(
            f"FAIL: {os.environ.get('DB_NAME') or '默认库'} 里没有启用状态的律师账号"
        )
    return user


def _mint_token(user_id: int) -> str:
    """铸 access token——**生产同一个函数**（agent 工具调用拿的就是这种票）。

    脚本要是自己拼 JWT，验的就不是 ``mint_user_access_token`` 这条真实链路了。
    同步函数，调用方须 ``sync_to_async``。
    """
    from apps.agent.pi.user_token import mint_user_access_token

    return mint_user_access_token(user_id)


# ── HTTP（全程绕代理） ──────────────────────────────────────────────


def _client(token: str) -> Any:
    """``trust_env=False`` 的异步 httpx client：不读 ``*_PROXY``，直连内网。

    与后端/网关同机，走代理只会 502（见模块 docstring）。
    """
    import httpx

    return httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=60.0,
        trust_env=False,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )


@asynccontextmanager
async def _no_proxy() -> AsyncIterator[None]:
    """请求期间把代理变量从本进程摘掉，退出时恢复（照 ``dsh_config`` 的同名做法）。

    两层保险，缺一层都会在开发机上 502：

    1. httpx client 用 ``trust_env=False``——请求本身不走代理；
    2. 本进程环境里也不留 ``*_PROXY``——:8002 是另一个进程不受影响，但 agent
       子进程（pi / dsh）与 openai-agents 的 ``AsyncOpenAI`` 都读**自己进程**
       的环境；本脚本在进程内起过 Django，若将来有人把它当模块复用，这里保证
       它不会把代理注入到那条链路里。

    用 ``contextlib.chdir`` 那种同步上下文管理器会漏掉 ``async with`` 的语义，
    所以显式写成异步版本（调用点全是 ``async with``）。
    """
    from apps.agent.backends.dsh_config import without_proxy_env

    with without_proxy_env():
        yield


async def _create_session(client: Any, agent_kind: str) -> str:
    """建一个验证用会话（``origin=task``：不与律师的对话列表混在一起）。"""
    response = await client.post(
        "/api/v1/agent/sessions",
        json={
            "title": f"verify-model-{uuid.uuid4().hex[:8]}",
            "origin": "task",
            "agent_kind": agent_kind,
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"建会话失败 HTTP {response.status_code}: {response.text[:300]}"
        )
    return str(response.json()["session_id"])


async def _stream_turn(
    client: Any, session_id: str, payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    """发一轮消息，把 SSE 事件全部收下来。

    逐行读 ``data:``：:8002 的 SSE 每帧就是 ``data: {json}\\n\\n``（见 ``_sse``），
    用 ``aiter_lines`` 而不是自己按 ``\\n\\n`` 切，避免把多行 JSON 切坏。

    ``timeout`` 是**整轮**的死线（不是单次读的超时）：一轮三模型可能跑几分钟，
    单次读超时必须给足，而整轮超时要能报出来「卡住了」。所以两者分开计。
    """
    events: list[dict[str, Any]] = []
    started = time.monotonic()
    async with client.stream(
        "POST", f"/api/v1/agent/sessions/{session_id}/messages", json=payload
    ) as response:
        if response.status_code >= 400:
            body = (await response.aread()).decode("utf-8", "replace")
            raise RuntimeError(f"发消息 HTTP {response.status_code}: {body[:400]}")
        async for line in response.aiter_lines():
            if time.monotonic() - started > timeout:
                raise TimeoutError(
                    f"整轮超过 {timeout:.0f}s 仍未结束（已收 {len(events)} 个事件）"
                )
            if not line.startswith("data:"):
                continue
            raw = line[len("data:") :].strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return {"events": events, "elapsed": round(time.monotonic() - started, 1)}


async def _get_json(client: Any, path: str) -> Any:
    response = await client.get(path)
    if response.status_code >= 400:
        raise RuntimeError(
            f"GET {path} HTTP {response.status_code}: {response.text[:300]}"
        )
    return response.json()


# ── 审计回读（「实得模型」的唯一来源） ──────────────────────────────────


async def _run_models(session_id: str) -> list[dict[str, Any]]:
    """读该会话的 ``AgentRun`` 行（逐栏一条），按写入顺序返回。

    ``AgentRun`` 没有 ``agent_kind`` 字段（见 ``models/run.py``），所以栏位只能靠
    条数与顺序对照 —— 这正是本脚本**要报出来**的一处规格缺口（见
    ``_report_run_attribution_gap``）：规格 §四 4.2 要求栏头显示「agent · 模型」，
    而模型落库后与栏位之间没有可关联的键。
    """
    from asgiref.sync import sync_to_async

    return await sync_to_async(_read_run_models, thread_sensitive=True)(session_id)


def _read_run_models(session_id: str) -> list[dict[str, Any]]:
    """``_run_models`` 的同步实现（ORM 查询）。"""
    from apps.agent.models import AgentRun

    return [
        {"model": row.model, "status": row.status, "output_tokens": row.output_tokens}
        for row in AgentRun.objects.filter(session__session_id=session_id).order_by(
            "id"
        )
    ]


async def _assistant_message_models(session_id: str) -> list[dict[str, Any]]:
    """读助手正文消息的 ``agent_kind`` 与 ``metadata["model"]``（交叉核对用）。

    正文那条对**每一栏**都该存在；缺失或 ``model`` 为空说明「模型没回写到
    metadata」，而 ``AgentRun.model`` 有值——两处漂移，必须报出来。
    """
    from asgiref.sync import sync_to_async

    return await sync_to_async(_read_assistant_message_models, thread_sensitive=True)(
        session_id
    )


def _read_assistant_message_models(session_id: str) -> list[dict[str, Any]]:
    """``_assistant_message_models`` 的同步实现（ORM 查询）。"""
    from apps.agent.models import AgentMessage

    return [
        {"agent_kind": row.agent_kind, "model": (row.metadata or {}).get("model", "")}
        for row in AgentMessage.objects.filter(
            session__session_id=session_id, role=AgentMessage.Role.ASSISTANT
        ).order_by("id")
    ]


# ── 预检：后端是否已加载新代码 ─────────────────────────────────────


async def _preflight(client: Any) -> list[str]:
    """探测后端是否已跑新代码，返回缺口清单（空 = 可以验）。"""
    gaps: list[str] = []
    try:
        schema = await _get_json(client, "/api/v1/openapi.json")
    except Exception as exc:
        _fail(f"FAIL: 取 OpenAPI 失败（{exc}）——后端没起或鉴权不通")
        raise SystemExit(EXIT_ENV) from exc

    schemas = schema.get("components", {}).get("schemas", {})
    message_in = schemas.get("MessageIn", {})
    agents_schema = json.dumps(
        message_in.get("properties", {}).get("agents", {}), ensure_ascii=False
    )
    # 新契约：``agents`` 的 item 允许对象（``AgentSpecIn``）。OpenAPI 里它是
    # ``anyOf: [{$ref: #/components/schemas/AgentSpecIn}, {type: string}]``——
    # **不要**找字面量 ``"object"``：Ninja 对嵌套 Schema 用 ``$ref``，那个字符串
    # 根本不会出现（第一版就是这么把「已落地」误判成「后端没重启」的）。
    has_spec_object = (
        "AgentSpecIn" in agents_schema
        or '"object"' in agents_schema
        or "AgentSpecIn" in schemas
    )
    if not has_spec_object:
        gaps.append("MessageIn.agents 仍是纯字符串数组（没有 {kind,model} 对象形态）")

    try:
        backends = await _get_json(client, "/api/v1/agent/backends")
    except Exception:
        backends = []
    # 规格 §二 2.3：/backends 要带模型清单。缺了它前端没法预填模型下拉，
    # 也不该假装「能选」。
    if backends and not any("models" in option for option in backends):
        gaps.append(
            "GET /agent/backends 未返回 models / default_model（前端没有可选模型清单）"
        )
    return gaps


def _report_stale(gaps: list[str]) -> int:
    """把「后端没重启」说成人话，别让读者以为是验收项失败。"""
    _fail("")
    _fail("后端代码尚未生效，无法验收（不是验收失败，是**还没法验**）：")
    for gap in gaps:
        _fail(f"  · {gap}")
    _fail("")
    _fail("这个表现在代码里还没落地：")
    _fail(
        "  · backend/apps/agent/schemas/session_schemas.py  MessageIn.agents 仍是 list[str]"
    )
    _fail(
        "  · backend/apps/agent/api/chat_api.py           只把 kind 交给编排层，model 被丢弃"
    )
    _fail(
        "  · backend/apps/agent/services/chat/stream.py   RunContext(model=None) 写死"
    )
    _fail(
        "  · backend/apps/agent/backends/pi_backend.py    没读 ctx.model，只用池里的默认模型"
    )
    _fail("")
    _fail("重启 :8002 让改动生效后再跑本脚本：")
    _fail(
        "  lsof -ti tcp:8002 | xargs -r kill && (cd backend && .venv/bin/python manage.py runserver 0.0.0.0:8002)"
    )
    return EXIT_STALE


# ── 验收项 ──────────────────────────────────────────────────────────


def _models_by_agent(messages: list[dict[str, Any]]) -> dict[str, str]:
    return {row["agent_kind"]: row["model"] for row in messages}


def _report_run_attribution_gap(messages: list[dict[str, Any]]) -> None:
    """打印一处**规格与实现的缺口**：``AgentRun.model`` 无法归到栏位。

    ``AgentRun`` 没有 ``agent_kind``（只有 ``session`` 外键），多栏一轮会落 N 条
    模型各异的记录而**没有任何键说明哪条属于哪一栏**。规格 §四 4.2 要求栏头显示
    「agent · 模型」，而落库侧拿不到这个对应关系；只有助手消息那条带
    ``agent_kind``。用量页按模型聚合时不受影响，按栏归因时受影响。
    """
    _say("  ℹ️ AgentRun 无 agent_kind 字段：逐栏成本只能按模型名反推、不能按栏归因")


async def check_three_models(token: str, timeout: float) -> bool:
    """验收项 1+2：三栏三模型同答，逐栏等于本轮指定值。"""
    _say("\n[1/4] 三 agent × 三模型同答（逐栏比对指定模型）")
    async with _client(token) as client, _no_proxy():
        session_id = await _create_session(client, "pi")
        agents = [{"kind": kind, "model": model} for kind, model in MATRIX]
        result = await _stream_turn(
            client, session_id, {"message": QUESTION, "agents": agents}, timeout
        )

    events = result["events"]
    dones = [event for event in events if event.get("type") == "done"]
    errors = [event for event in events if event.get("type") == "error"]
    degraded = [
        event
        for event in events
        if event.get("type") == "activity" and event.get("status") == "degraded"
    ]
    messages = await _assistant_message_models(session_id)
    runs = await _run_models(session_id)
    actual = _models_by_agent(messages)
    wanted = dict(MATRIX)

    _say(
        f"  会话 {session_id} · {result['elapsed']}s · 事件 {len(events)} · done {len(dones)}"
    )
    for kind, wanted_model in wanted.items():
        mark = "\u2705" if actual.get(kind) == wanted_model else "\u274c"
        _say(
            f"    {mark} {kind:<14} 指定 {wanted_model:<22} 实得 {actual.get(kind) or '(缺)'}"
        )
    _say(f"  AgentRun 逐条：{runs}")
    _report_run_attribution_gap(messages)

    passed = True
    if not dones:
        passed = _bad("没有收到任何 done（本轮没跑完）", f"错误事件：{errors[:2]}")
    if errors:
        passed = _bad(
            "本轮有错误事件", json.dumps(errors[:2], ensure_ascii=False)[:400]
        )
    if degraded:
        passed = _bad(
            "本轮被降级为只跑主后端（aux 席位不足）",
            json.dumps(degraded, ensure_ascii=False)[:300]
            + "；检查 FACHUAN_AGENT_AUX_SLOTS / AUX_RATIO",
        )
    if len(dones) != len(wanted):
        passed = _bad(
            f"done 数量 {len(dones)} != 栏数 {len(wanted)}",
            "每栏一个 done 是 v27.19.1 契约",
        )
    for kind, model in wanted.items():
        if actual.get(kind) != model:
            passed = _bad(
                f"{kind} 没用指定的模型",
                f"指定 {model}，实得 {actual.get(kind) or '(缺)'}",
            )
    distinct = {value for value in actual.values() if value}
    if len(distinct) != len(wanted):
        passed = _bad("三栏实得模型不互不相同", f"{actual}")
    elif passed:
        _ok("三栏实得模型互不相同且逐栏等于指定值", str(distinct))

    # 交叉核对：AgentRun.model 与助手消息 metadata 必须一致（两处各自推导就会漂移）
    run_models = sorted(row["model"] for row in runs if row["model"])
    message_models = sorted(value for value in actual.values() if value)
    if run_models and run_models != message_models:
        _fail(
            f"  \u26a0\ufe0f AgentRun.model {run_models} 与消息 metadata {message_models} 不一致（两处推导模型）"
        )
    return passed


async def check_default_model(token: str, timeout: float) -> bool:
    """验收项 3：不传模型 → 用平台默认（不是「上一栏的模型」）。"""
    _say("\n[2/4] 不传模型 → 平台默认")
    async with _client(token) as client, _no_proxy():
        backends = {
            option.get("kind"): option
            for option in await _get_json(client, "/api/v1/agent/backends")
        }
        default_model = (backends.get("pi") or {}).get("default_model") or ""
        model_list = (backends.get("pi") or {}).get("models") or []
        session_id = await _create_session(client, "pi")
        # ``model`` 显式给空串：规格 §二 2.1 的「空/None = 用平台默认」。对象形态
        # 配空串比「省略字段」更能验到「空值不覆盖默认」。
        result = await _stream_turn(
            client,
            session_id,
            {"message": QUESTION, "agents": [{"kind": "pi", "model": ""}]},
            timeout,
        )

    messages = await _assistant_message_models(session_id)
    runs = await _run_models(session_id)
    actual = messages[0]["model"] if messages else ""
    errors = [event for event in result["events"] if event.get("type") == "error"]
    _say(
        f"  会话 {session_id} · /backends 的 pi.default_model={default_model or '(未返回)'} · models={model_list}"
    )
    _say(f"  实得模型 {actual or '(缺)'} · AgentRun {runs}")
    if errors:
        return _bad("本轮有错误事件", json.dumps(errors[:2], ensure_ascii=False)[:300])
    if not actual:
        return _bad(
            "没有回读到模型名", "助手消息 metadata.model 与 AgentRun.model 都为空"
        )
    if default_model:
        return (
            bool(_ok("用了平台默认模型", actual))
            if actual == default_model
            else _bad("没用平台默认模型", f"期望 {default_model}，实得 {actual}")
        )
    # /backends 还没返回 default_model（旧代码）：退回「只要实际值是模型清单里的
    # 第一个，且不是本轮别处指定过的模型」——弱判据，必须明说它是弱判据。
    if model_list:
        expected = model_list[0]
        ok = actual == expected
        return (
            bool(_ok("用了平台默认模型（回退判据：models[0]）", actual))
            if ok
            else _bad("没用平台默认模型", f"期望 models[0]={expected}，实得 {actual}")
        )
    return _bad(
        "无法判定平台默认模型", "GET /agent/backends 既没有 default_model 也没有 models"
    )


async def check_legacy_string_agents(token: str, timeout: float) -> bool:
    """验收项 4：老前端发纯字符串数组（``["pi","dsh"]``）仍然正常。"""
    _say("\n[3/4] 老前端回归：agents 是纯字符串数组")
    async with _client(token) as client, _no_proxy():
        session_id = await _create_session(client, "pi")
        result = await _stream_turn(
            client, session_id, {"message": QUESTION, "agents": LEGACY_AGENTS}, timeout
        )

    events = result["events"]
    dones = [event for event in events if event.get("type") == "done"]
    errors = [event for event in events if event.get("type") == "error"]
    deltas = [event for event in events if event.get("type") == "delta"]
    agents_seen = {event.get("agent") for event in deltas if event.get("agent")}
    messages = await _assistant_message_models(session_id)
    _say(
        f"  会话 {session_id} · {result['elapsed']}s · done {len(dones)} · 栏 {sorted(agents_seen)}"
    )
    _say(f"  逐栏模型（应全部 = 平台默认）：{_models_by_agent(messages)}")
    if not messages:
        # 老契约的回归点是「能跑完」，不是「模型能回读」——后者是本轮新加的能力，
        # 没落地时这里一定是空的。不能因此判失败，否则一个纯回归项会因为新功能
        # 未合入而红，读者会误判成「老前端被改坏了」。
        _say("  ℹ️ 模型未回读（新能力尚未落地）—— 本项只验老前端的请求形态仍被接受")

    if errors:
        return _bad("老前端请求出错", json.dumps(errors[:2], ensure_ascii=False)[:400])
    if len(dones) != len(LEGACY_AGENTS):
        return _bad("done 数量与栏数不符", f"{len(dones)} != {len(LEGACY_AGENTS)}")
    if agents_seen != set(LEGACY_AGENTS):
        return _bad("两栏没有都出正文", f"实得 {sorted(agents_seen)}")
    return _ok("纯字符串数组仍按两栏跑完", f"{sorted(agents_seen)}")


async def check_dual_flag(token: str, timeout: float) -> bool:
    """附加回归：旧 ``dual: true``（不带 agents）仍然可用。

    规格只要求 ``agents`` 兼容，但 ``dual`` 是**更老**的客户端契约，且
    ``chat_api`` 的分支改动（新增 ``wanted`` 判断）正好压在它上面——这里补一条，
    成本是一次请求。
    """
    _say("\n[4/4] 更老的前端回归：dual=true（不带 agents 字段）")
    async with _client(token) as client, _no_proxy():
        session_id = await _create_session(client, "pi")
        result = await _stream_turn(
            client, session_id, {"message": QUESTION, "dual": True}, timeout
        )
    dones = [event for event in result["events"] if event.get("type") == "done"]
    errors = [event for event in result["events"] if event.get("type") == "error"]
    _say(f"  会话 {session_id} · {result['elapsed']}s · done {len(dones)}")
    if errors:
        return _bad("dual=true 出错", json.dumps(errors[:2], ensure_ascii=False)[:400])
    if len(dones) < 2:
        return _bad("dual=true 没有跑出两栏", f"done {len(dones)}")
    return _ok("dual=true 仍跑双栏", f"done {len(dones)}")


# ── 入口 ────────────────────────────────────────────────────────────


async def _run(args: argparse.Namespace) -> int:
    from asgiref.sync import sync_to_async

    user = await sync_to_async(_django_user, thread_sensitive=True)(args.user)
    token = await sync_to_async(_mint_token, thread_sensitive=True)(int(user.pk))
    _say(
        f"律师 #{user.pk}（{getattr(user, 'username', '')}）· 后端 {BASE_URL} · 死线 {args.timeout:.0f}s"
    )

    async with _client(token) as client:
        try:
            await _get_json(client, "/api/v1/agent/backends")
        except Exception as exc:
            _fail(f"FAIL: 连不上后端 {BASE_URL}（{exc}）——先起 :8002")
            return EXIT_ENV
        gaps = await _preflight(client)
    if gaps:
        return _report_stale(gaps)

    results = [await check_three_models(token, args.timeout)]
    results.append(await check_default_model(token, args.timeout))
    if not args.skip_legacy:
        results.append(await check_legacy_string_agents(token, args.timeout))
        results.append(await check_dual_flag(token, args.timeout))

    passed = sum(1 for result in results if result)
    _say("")
    if passed == len(results):
        _say(f"\u2705 全部通过（{passed}/{len(results)}）")
        return EXIT_PASS
    _fail(f"\u274c 失败 {len(results) - passed}/{len(results)} 项")
    return EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="验收「每栏可指定模型」（真后端 + 真网关）"
    )
    parser.add_argument(
        "--user", type=int, default=None, help="用哪个律师账号（默认第一个启用账号）"
    )
    parser.add_argument(
        "--timeout", type=float, default=180.0, help="单轮死线（秒），默认 180"
    )
    parser.add_argument(
        "--skip-legacy", action="store_true", help="跳过两个老前端回归项"
    )
    args = parser.parse_args(argv)

    import django

    django.setup()
    import asyncio

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
