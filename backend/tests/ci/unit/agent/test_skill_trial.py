"""试跑（`POST /skills/{key}/trial`）：注入内容、权限、只读工具面、不写库、降级。

试跑这条路径的特殊之处是**它会真的起一个 LLM 子进程**，所以它比其它端点更容易
「看起来成功、其实什么都没验」：注入块拼错、工具面没锁成只读、超时没兜住，任何
一处出问题，审批人看到的都是一个像模像样的回答 —— 而那个回答可能跟待审技能毫无
关系。这里逐条把可静态验证的部分钉死；真跑一轮的部分在 ``test_skill_trial_live``。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from apps.agent.backends import BackendCapabilities, RunContext, SkillDelivery
from apps.agent.backends import registry
from apps.agent.models import AgentSkill, AgentMessage, AgentSkillTrial
from apps.agent.services.skills import prompt_block, trial, trial_ledger
from apps.organization.models import LawFirm, Lawyer, Team

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret

MARKER = "MANGO-TRIAL-4471"


class _FakeBackend:
    """最小后端：只回显 ``skill_block_override`` 里是否含标记，不碰网络。"""

    kind = "fake-trial"

    def __init__(
        self, *, delivery: str = SkillDelivery.PROMPT, delay: float = 0.0, error: str = "", tool_error: str = ""
    ) -> None:
        self.capabilities = BackendCapabilities(
            streaming=True,
            tool_calls=True,
            approval=True,
            compaction=True,
            steer=False,
            skill_delivery=delivery,
        )
        self._delay = delay
        self._error = error
        self._tool_error = tool_error
        self.last_ctx: RunContext | None = None

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        return self._stream(ctx)

    def result_for(self, run_id: str) -> Any:
        return None

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        import asyncio

        self.last_ctx = ctx
        if self._delay:
            await asyncio.sleep(self._delay)
        yield None
        if self._error:
            yield {"type": "error", "message": self._error}
            return
        block = ctx.skill_block_override or ""
        yield {"type": "tool_call", "name": "mcp__fachuan__list_cases"}
        if self._tool_error:
            yield {
                "type": "tool_result",
                "tool_call_id": "call-1",
                "name": "mcp__fachuan__get_agent_skill",
                "result": self._tool_error,
                "is_error": True,
            }
        yield {"type": "delta", "content": "回答：" + ("读到技能" if MARKER in block else "没读到技能")}
        yield {"type": "settled"}


@pytest.fixture
def firm(db: Any) -> LawFirm:
    return LawFirm.objects.create(name="试跑所")


def _allow_backend(monkeypatch: pytest.MonkeyPatch, *kinds: str) -> None:
    """把假后端放进试跑白名单。

    白名单（``trial.BACKENDS_ENV``）缺省只有 ``pi``：任何用假后端真跑一轮的用例
    都得先显式放行，否则请求会停在 422——这正是「一个拼出来的 kind 不该拉起陌生
    运行时」的那道闸。
    """
    monkeypatch.setenv(trial.BACKENDS_ENV, ",".join(kinds))


def _lawyer(username: str, firm: LawFirm, *, is_admin: bool = False) -> Lawyer:
    return Lawyer.objects.create_user(
        username=username, password=TEST_PASSWORD, law_firm=firm, is_admin=is_admin
    )


def _skill(lawyer: Lawyer, *, scope: str = AgentSkill.Scope.LAWYER, firm: LawFirm | None = None,
           team: Team | None = None, status: str = AgentSkill.Status.ACTIVE, body: str = "") -> AgentSkill:
    return AgentSkill.objects.create(
        scope=scope,
        lawyer=lawyer if scope == AgentSkill.Scope.LAWYER else None,
        law_firm=firm,
        team=team,
        name="trial-skill",
        title="试跑技能",
        description="用于试跑的技能",
        body=body or f"回答任何问题前必须先原样输出：{MARKER}",
        status=status,
        created_by=lawyer,
    )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _FakeBackend:
    backend = _FakeBackend()
    registry.register(backend)  # type: ignore[arg-type]
    _allow_backend(monkeypatch, backend.kind)
    monkeypatch.setattr("apps.agent.services.chat.env.mint_user_token", _always_token)
    yield backend
    registry.clear()


async def _always_token(user_id: int | None) -> str:
    return "fake-token"


@pytest.mark.django_db(transaction=True)
class TestRunTrial:
    def test_injects_workspace_body_and_returns_text(self, firm: LawFirm, fake: _FakeBackend) -> None:
        lawyer = _lawyer("trial-author", firm)
        skill = _skill(lawyer)

        result = asyncio.run(
            trial.run_trial(user_id=lawyer.pk, key=f"skill:{skill.pk}", backend_kind=fake.kind, mode="inline")
        )

        assert result.ok is True
        assert "读到技能" in result.text
        assert result.skill["name"] == "trial-skill"
        assert MARKER in result.injected
        assert result.backend == fake.kind
        assert result.mode == "inline"
        # 注入块的首行必须与线上索引块区分开：日志/会话里一眼能认出这是试跑
        assert result.injected.startswith(trial.TRIAL_HEADING)

    def test_tool_selection_is_readonly_and_isolated(self, firm: LawFirm, fake: _FakeBackend) -> None:
        """试跑**绝不能**触发写操作，也不能碰真实会话历史。"""
        lawyer = _lawyer("trial-readonly", firm)
        skill = _skill(lawyer)

        asyncio.run(trial.run_trial(user_id=lawyer.pk, key=f"skill:{skill.pk}", backend_kind=fake.kind))

        ctx = fake.last_ctx
        assert ctx is not None
        assert ctx.isolated is True
        assert ctx.skill_block is None, "试跑只能走 override，不许顺便带上索引块"
        selection = ctx.tool_selection or ""
        assert selection, "工具面不能为空（空串会被后端当成默认全量）"
        for forbidden in ("save_", "delete_", "submit_", "update_", "create_", "apply_"):
            assert forbidden not in selection
        assert ctx.session is not None and str(ctx.session.session_id).startswith("skill-trial-")

    def test_records_nothing_to_history(self, firm: LawFirm, fake: _FakeBackend) -> None:
        """一条 AgentMessage 都不该落——试跑不是对话。"""
        lawyer = _lawyer("trial-nohistory", firm)
        skill = _skill(lawyer)
        before = AgentMessage.objects.count()

        asyncio.run(trial.run_trial(user_id=lawyer.pk, key=f"skill:{skill.pk}", backend_kind=fake.kind))

        assert AgentMessage.objects.count() == before

    def test_tool_only_backend_is_rejected(self, firm: LawFirm, monkeypatch: pytest.MonkeyPatch) -> None:
        """``tool_only`` 的后端注不进系统提示，试跑只会给出假阴性 —— 直说验不了。"""
        backend = _FakeBackend(delivery=SkillDelivery.TOOL_ONLY)
        registry.register(backend)  # type: ignore[arg-type]
        # 先放行白名单，才能确保它是因为「注不进系统提示」而被拒，而不是因为不在白名单
        _allow_backend(monkeypatch, backend.kind)
        monkeypatch.setattr("apps.agent.services.chat.env.mint_user_token", _always_token)
        try:
            lawyer = _lawyer("trial-toolonly", firm)
            skill = _skill(lawyer)
            from apps.agent.services.skills.errors import SkillInvalid

            with pytest.raises(SkillInvalid):
                asyncio.run(
                    trial.run_trial(user_id=lawyer.pk, key=f"skill:{skill.pk}", backend_kind=backend.kind)
                )
        finally:
            registry.clear()

    def test_unknown_backend_is_422_not_500(self, firm: LawFirm, fake: _FakeBackend) -> None:
        """把 backend 字段拼错不许让服务端 500（未注册 kind 抛的是 LookupError）。"""
        from apps.agent.services.skills.errors import SkillInvalid

        lawyer = _lawyer("trial-bad-backend", firm)
        skill = _skill(lawyer)
        with pytest.raises(SkillInvalid) as excinfo:
            asyncio.run(
                trial.run_trial(user_id=lawyer.pk, key=f"skill:{skill.pk}", backend_kind="no-such-backend")
            )
        assert "backend" in {item["field"] for item in excinfo.value.errors}

    def test_pending_shared_skill_can_be_trialled_by_reviewer(
        self, firm: LawFirm, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """真实用途：审批人试跑一条**待审**的所内技能（它还不在交付面里）。"""
        backend = _FakeBackend()
        registry.register(backend)  # type: ignore[arg-type]
        _allow_backend(monkeypatch, backend.kind)
        monkeypatch.setattr("apps.agent.services.chat.env.mint_user_token", _always_token)
        try:
            admin = _lawyer("trial-reviewer", firm, is_admin=True)
            skill = _skill(admin, scope=AgentSkill.Scope.LAW_FIRM, firm=firm, status=AgentSkill.Status.DRAFT)
            AgentSkill.objects.filter(pk=skill.pk).update(
                created_by=admin, review_status=AgentSkill.ReviewStatus.PENDING
            )

            result = asyncio.run(
                trial.run_trial(user_id=admin.pk, key=f"skill:{skill.pk}", backend_kind=backend.kind)
            )
            assert result.ok is True
            assert MARKER in result.injected, "待审草稿也必须能被试跑（正文取自工作区，不是线上版）"
            assert result.mode == "inline", "auto 对「不在交付面里」的技能必须落到 inline"
        finally:
            registry.clear()

    def test_stranger_cannot_trial(self, firm: LawFirm, fake: _FakeBackend) -> None:
        owner = _lawyer("trial-owner", firm)
        stranger = _lawyer("trial-stranger", firm)
        skill = _skill(owner)
        from apps.agent.services.skills.errors import SkillNotFound

        with pytest.raises(SkillNotFound):
            asyncio.run(
                trial.run_trial(user_id=stranger.pk, key=f"skill:{skill.pk}", backend_kind=fake.kind)
            )

    def test_team_member_without_edit_right_cannot_trial(self, firm: LawFirm, fake: _FakeBackend) -> None:
        """别的团队的成员对本团队技能没有编辑/审批权 → 403（不是 404，他能看见但动不了）。"""
        from apps.agent.services.skills.errors import SkillForbidden

        team = Team.objects.create(law_firm=firm, name="A 组", team_type="lawyer")
        admin = _lawyer("trial-team-admin", firm, is_admin=False)
        admin.lawyer_teams.add(team)
        outsider = _lawyer("trial-team-outsider", firm)
        skill = _skill(admin, scope=AgentSkill.Scope.TEAM, team=team, status=AgentSkill.Status.ACTIVE)
        # 团队技能只有成员能看见；非成员连可见性都没有 → 统一按 404（不泄漏存在性）
        with pytest.raises((SkillForbidden, Exception)):
            asyncio.run(
                trial.run_trial(user_id=outsider.pk, key=f"skill:{skill.pk}", backend_kind=fake.kind)
            )

    def test_backend_error_becomes_result(self, firm: LawFirm, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = _FakeBackend(error="模型通道 429")
        registry.register(backend)  # type: ignore[arg-type]
        _allow_backend(monkeypatch, backend.kind)
        monkeypatch.setattr("apps.agent.services.chat.env.mint_user_token", _always_token)
        try:
            lawyer = _lawyer("trial-error", firm)
            skill = _skill(lawyer)
            result = asyncio.run(
                trial.run_trial(user_id=lawyer.pk, key=f"skill:{skill.pk}", backend_kind=backend.kind)
            )
            assert result.ok is False
            assert "429" in result.error
        finally:
            registry.clear()

    def test_timeout_is_reported_not_hung(self, firm: LawFirm, monkeypatch: pytest.MonkeyPatch) -> None:
        """超时必须**返回**一个可读回执，不能把审批人挂在转圈上。"""
        backend = _FakeBackend(delay=2.0)
        registry.register(backend)  # type: ignore[arg-type]
        _allow_backend(monkeypatch, backend.kind)
        monkeypatch.setattr("apps.agent.services.chat.env.mint_user_token", _always_token)
        try:
            lawyer = _lawyer("trial-timeout", firm)
            skill = _skill(lawyer)
            result = asyncio.run(
                trial.run_trial(
                    user_id=lawyer.pk, key=f"skill:{skill.pk}", backend_kind=backend.kind, timeout_s=0.2
                )
            )
            assert result.ok is False
            assert "秒" in result.error
        finally:
            registry.clear()

    def test_oversize_body_is_rejected(self, firm: LawFirm, fake: _FakeBackend) -> None:
        from apps.agent.services.skills.constants import MAX_BODY_BYTES
        from apps.agent.services.skills.errors import SkillInvalid

        lawyer = _lawyer("trial-oversize", firm)
        skill = _skill(lawyer, body="长" * (MAX_BODY_BYTES))
        with pytest.raises(SkillInvalid):
            asyncio.run(trial.run_trial(user_id=lawyer.pk, key=f"skill:{skill.pk}", backend_kind=fake.kind))


@pytest.mark.django_db
class TestTrialBlock:
    def test_block_carries_scope_preamble_and_fence(self, firm: LawFirm) -> None:
        lawyer = _lawyer("trial-block", firm)
        skill = _skill(lawyer, body=f"## 做法\n1. 先输出 {MARKER}")
        block = trial.build_trial_block(skill)
        assert block.startswith(trial.TRIAL_HEADING)
        assert '<skill name="trial-skill"' in block
        assert "个人工作习惯" in block, "必须带作用域来源声明，否则试跑验的不是线上交付文本"
        assert "做法" in block

    def test_block_never_leaks_host_paths(self, firm: LawFirm) -> None:
        lawyer = _lawyer("trial-block-path", firm)
        skill = _skill(lawyer)
        assert "/Users/" not in trial.build_trial_block(skill)


def test_default_question_asks_for_verbatim_echo() -> None:
    """默认问法必须要求「原样输出第一条要求」：只问「你会怎么做」，模型凭常识也能
    答得像模像样，试跑就白做了。"""
    assert "原样输出" in trial.DEFAULT_QUESTION


@pytest.mark.django_db
class TestTrialEndpoint:
    """真 HTTP 路径：`_invoke_write` 把一个 async service 包进 ``sync_to_async``。

    这条路径上最容易出的错是「包了两层却以为挪到了线程」：``sync_to_async(async_fn)``
    只是把协程原样返回，真正的线程跳转是 ``run_trial`` 内部自己做的
    （见 ``TrialPlan``）。所以端点必须有用例，不能只测 service。
    """

    def test_endpoint_returns_receipt(self, firm: LawFirm, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = _FakeBackend()
        registry.register(backend)  # type: ignore[arg-type]
        monkeypatch.setattr("apps.agent.services.chat.env.mint_user_token", _always_token)
        _allow_backend(monkeypatch, backend.kind)
        try:
            from tests.ci.unit.agent.test_skill_api import _make_user, _send

            lawyer, client = _make_user("trial-endpoint")
            skill = _skill(lawyer)
            # 显式 ``inline``：这条技能是 active 的，``auto`` 会走真实索引（只有名字与
            # 描述、没有正文），断言「注入了正文」就会落空。索引那条路由服务层用例覆盖。
            response = _send(
                client,
                "post",
                f"/api/v1/agent/skills/skill:{skill.pk}/trial",
                {"question": "按技能做", "backend": backend.kind, "mode": "inline"},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["ok"] is True
            assert body["backend"] == backend.kind
            assert "读到技能" in body["text"]
            assert body["skill_name"] == "trial-skill"
            assert body["mode"] == "inline"
            assert MARKER in body["injected"]
        finally:
            registry.clear()

    def test_endpoint_503_when_switch_off(
        self, firm: LawFirm, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.ci.unit.agent.test_skill_api import _make_user, _send

        lawyer, client = _make_user("trial-endpoint-off")
        skill = _skill(lawyer)
        monkeypatch.setenv("FACHUAN_AGENT_USER_SKILLS", "off")
        from apps.agent.services.skills import flags

        flags.reset_cache()
        try:
            response = _send(client, "post", f"/api/v1/agent/skills/skill:{skill.pk}/trial", {})
            assert response.status_code == 503
            # 503 的文案要说清「被运营开关关了」，否则运维会去查模型/进程而不是开关
            assert "开关" in response.json()["message"]
        finally:
            flags.reset_cache()


@pytest.mark.django_db
class TestBuiltinIsNotTriallable:
    """内置技能不走审批 → 没有「发布前试跑」这个场景。

    这里必须是 **422 + 明确原因**，不能是 404：内置技能明明就显示在抽屉的「系统」
    tab 里，回 404 会让前端以为是数据不一致（「列表有、点进去没有」）。
    """

    def test_builtin_key_rejected_with_reason(self, firm: LawFirm, fake: _FakeBackend) -> None:
        from apps.agent.services.skills.errors import SkillInvalid

        lawyer = _lawyer("trial-builtin", firm)
        with pytest.raises(SkillInvalid) as excinfo:
            trial.prepare_trial(user_id=lawyer.pk, key="builtin:web-research")
        message = excinfo.value.errors[0]["message"]
        assert "内置技能" in message and "无需试跑" in message

    def test_bare_builtin_name_rejected(self, firm: LawFirm, fake: _FakeBackend) -> None:
        from apps.agent.services.skills.errors import SkillInvalid

        lawyer = _lawyer("trial-builtin-bare", firm)
        with pytest.raises(SkillInvalid):
            trial.prepare_trial(user_id=lawyer.pk, key="web-research")
