"""技能送达接线：工具面不变量、隔离强制空块、``/skill:`` 在真实锚点前缀下展开。

这篇守的是「技能真的到了模型面前」这一层，而不是渲染本身（渲染在
``test_skill_prompt_block`` / ``test_skill_expand`` 里测）。四类事故各一条用例：

1. **工具面被技能参数带歪**：``--append-system-prompt`` 里有中文标题与技能名，
   只要参数拼装顺序一变，``--tools`` 就可能被顶掉或降级——四个内置文件工具
   （read/bash/edit/write）一旦回来，一段藏在工具输出里的注入就能免审批执行。
2. **隔离运行偷带技能**：综合结论是对几栏回答的客观合并，律师的个人技能与所内
   索引会把无关工作流混进去；「无 override 就必须是空块」是不变量门禁
   （CONTRACT §12 #4）。
3. **发布前试跑注不进待审技能**：试跑要验证的正是「只装这一条会怎样」，
   ``skill_block_override`` 必须能绕过 ``isolated=True`` 的强制空块。
4. **详情页里 ``/skill:`` 静默失效**：``[当前业务：…]`` 前缀把命令顶离行首，
   pi 原生展开只认 ``text.startsWith("/skill:")``——这条链路一旦断，律师看到的
   只是「模型没按我的规范回答」，没有任何报错。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from apps.agent.backends import RunContext, SkillDelivery
from apps.agent.pi import rpc_client
from apps.agent.services.skills import prompt_block
from apps.organization.models import LawFirm, Lawyer

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret

#: 随代码发布的内置技能（正文非空，展开用例不需要造数据）
BUILTIN = "web-research"

#: 详情页每轮前置的锚点行（``store/turn-send.ts`` 拼的就是这个形状）
BIZ_ANCHOR = "[当前业务：本委托“某银行” contract_id=8]"


class TestPiToolFaceInvariant:
    """``--tools`` 恒等于 ``TOOL_SELECTION``，与技能注入参数无关（CONTRACT §12 #1）。"""

    def test_tools_stay_mcp_whitelist_with_append_block(self) -> None:
        session = rpc_client.PiRpcSession(
            cwd="/tmp/work",
            extension_path="/tmp/approval-gate.ts",
            append_system_prompt=f"{prompt_block.BLOCK_HEADING}\n- [我的] {BUILTIN}：《检索》——查资料",
        )
        args = session._build_args("/usr/local/bin/pi")
        assert args[args.index("--tools") + 1] == rpc_client.TOOL_SELECTION
        selection = rpc_client.TOOL_SELECTION
        for banned in ("read", "bash", "edit", "write"):
            assert banned not in selection

    def test_skill_delivery_declared_prompt(self) -> None:
        """声明 ``PROMPT`` 就等于承诺真的注入了索引块（见 ``base.py`` 的字段说明）。"""
        from apps.agent.backends.pi_backend import PiBackend

        assert PiBackend.capabilities.skill_delivery == SkillDelivery.PROMPT


class _StubPiSession:
    """够 ``PiBackend`` 跑完一轮的最小 pi 会话桩（不拉子进程）。"""

    turns_started = 0

    async def prompt(self, message: str) -> None:
        return None

    async def get_session_stats(self) -> dict[str, Any]:
        return {}

    async def abort(self) -> bool:
        return True


class _RecordingPool:
    """记下 ``acquire`` 收到的全部关键字参数（隔离与技能块的断言都读它）。"""

    waiting = 0
    saturated = False

    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def acquire(self, **kwargs: Any) -> Any:
        # 原地更新而不是重新绑定：fixture 把一份**同一个 dict** 交给用例，
        # 重新绑定会让断言读到 acquire 之前的空快照。
        self.kwargs.clear()
        self.kwargs.update(kwargs)
        session = _StubPiSession()

        class _Acquire:
            async def __aenter__(self) -> _StubPiSession:
                return session

            async def __aexit__(self, *exc: object) -> bool:
                return False

        return _Acquire()


class _FakeLiveRegistry:
    """运行中登记表的空实现：本轮不关心插话，但 ``PiBackend`` 会调它。"""

    async def register(self, session_id: str, session: Any) -> None:
        return None

    async def unregister(self, session_id: str, session: Any) -> None:
        return None


class _Session:
    session_id = "sess-delivery"


def _ctx(**overrides: Any) -> RunContext:
    fields: dict[str, Any] = {
        "run_id": "sess-delivery:pi:1",
        "session": _Session(),
        "user_id": None,
        "prompt": "你好",
        "user_token": "tok",
        "model": "kimi-2.6",
        "tool_selection": None,
    }
    fields.update(overrides)
    return RunContext(**fields)


@pytest.fixture()
def pi_acquire_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """把 ``pi_pool.get_pool`` / 模型解析 / 事件流 / 登记表全换成桩，返回 ``acquire`` 实参。"""
    pool = _RecordingPool()

    async def fake_get_pool() -> Any:
        return pool

    async def fake_model() -> str | None:
        return "kimi-2.6"

    async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
        yield {"type": "delta", "content": "答"}
        yield {"type": "done"}

    monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool.get_pool", fake_get_pool)
    monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool._resolve_model", fake_model)
    monkeypatch.setattr("apps.agent.backends.pi_backend.stream_events", fake_stream)
    monkeypatch.setattr("apps.agent.backends.pi_backend.get_live_registry", lambda: _FakeLiveRegistry())
    monkeypatch.setattr("apps.agent.backends.pi_backend.register_live_route", lambda *a, **k: None)
    monkeypatch.setattr("apps.agent.backends.pi_backend.unregister_live_route", lambda *a, **k: None)
    return pool.kwargs


def _drain(ctx: RunContext) -> list[dict[str, Any]]:
    from apps.agent.backends.pi_backend import PiBackend

    async def run() -> list[dict[str, Any]]:
        return [event async for event in PiBackend().stream(ctx) if event is not None]

    return asyncio.run(run())


class TestIsolatedSkillBlock:
    """``isolated=True`` 的技能块判据（``base.py`` 的不变量门禁）。"""

    def test_isolated_without_override_injects_nothing(self, pi_acquire_kwargs: dict[str, Any]) -> None:
        _drain(_ctx(isolated=True, skill_block=f"{prompt_block.BLOCK_HEADING}\n- [我的] x：《x》"))
        assert pi_acquire_kwargs["append_system_prompt"] is None
        # 技能目录同时恒为空：``--no-skills`` + 零路径 = 零宿主技能
        assert pi_acquire_kwargs["skill_paths"] == []

    def test_isolated_with_override_injects_override_only(self, pi_acquire_kwargs: dict[str, Any]) -> None:
        override = f"{prompt_block.BLOCK_HEADING}\n- [我的] draft：《待审技能》——试跑"
        _drain(_ctx(isolated=True, skill_block="稳定的索引块", skill_block_override=override))
        assert pi_acquire_kwargs["append_system_prompt"] == override

    def test_regular_run_passes_context_block(self, pi_acquire_kwargs: dict[str, Any]) -> None:
        block = f"{prompt_block.BLOCK_HEADING}\n- [所内] contract-review：《合同审查》"
        _drain(_ctx(skill_block=block))
        assert pi_acquire_kwargs["append_system_prompt"] == block


@pytest.fixture
def delivery_lawyer(db: Any) -> Lawyer:
    firm = LawFirm.objects.create(name="技能送达所")
    return Lawyer.objects.create_user(username="delivery-user", password=TEST_PASSWORD, law_firm=firm)


@pytest.fixture()
def prepared_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """把「铸凭证」与「探 pi session」换成桩：本组用例只测展开与索引块。"""

    async def fake_mint(user_id: int | None) -> str:
        return "tok" if user_id is not None else ""

    async def fake_resume(session_id: str) -> bool:
        return True

    monkeypatch.setattr("apps.agent.services.chat.stream.env.mint_user_token", fake_mint)
    monkeypatch.setattr("apps.agent.services.chat.stream.probe_pi_session", fake_resume)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_prepare_context_expands_skill_behind_business_anchor(
    prepared_env: None, delivery_lawyer: Lawyer
) -> None:
    """详情页真实形态：锚点在前、``/skill:`` 在后，展开必须命中且锚点保留。"""
    from apps.agent.services.chat.stream import prepare_context
    from apps.agent.services.session_service import create_session

    session = await create_session(title="展开", user_id=delivery_lawyer.pk)
    context = await prepare_context(
        session=session,
        user_id=delivery_lawyer.pk,
        user_message=f"{BIZ_ANCHOR}\n/skill:{BUILTIN} 查一下最新判例",
    )
    assert context.expanded_skill is not None
    assert context.expanded_skill["name"] == BUILTIN
    assert "<skill " in context.prompt_text
    # 锚点原样拼回：模型仍要知道「这是哪个案件」
    assert context.prompt_text.startswith(BIZ_ANCHOR)
    # 正文里不得出现宿主机绝对路径（pi 原生展开的已知泄露面）
    assert "/Users/" not in context.prompt_text


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_skill_block_empty_when_user_skills_off(
    prepared_env: None, delivery_lawyer: Lawyer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``FACHUAN_AGENT_USER_SKILLS=off`` → 提示块空（CONTRACT §12 #5）。"""
    from apps.agent.services.chat.stream import prepare_context
    from apps.agent.services.session_service import create_session

    monkeypatch.setenv("FACHUAN_AGENT_USER_SKILLS", "off")
    session = await create_session(title="关开关", user_id=delivery_lawyer.pk)
    context = await prepare_context(session=session, user_id=delivery_lawyer.pk, user_message="你好")
    assert context.skill_block == ""


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_skill_block_rendered_when_enabled(prepared_env: None, delivery_lawyer: Lawyer) -> None:
    """开关打开时索引块真的带内容，且块首是给 pi 的「非文件路径」形状保险。"""
    from apps.agent.services.chat.stream import prepare_context
    from apps.agent.services.session_service import create_session

    session = await create_session(title="开索引", user_id=delivery_lawyer.pk)
    context = await prepare_context(session=session, user_id=delivery_lawyer.pk, user_message="你好")
    assert context.skill_block.startswith(prompt_block.BLOCK_HEADING)
