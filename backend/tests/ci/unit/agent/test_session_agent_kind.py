"""会话的 agent 后端选择（AgentSession.agent_kind）。

引入这个字段的目的是「同一律师可以在不同会话里用不同 agent」。三个验收点：

1. **默认与历史数据一致**：不传 agent_kind 时落到 `pi`，与引入字段前完全等价
   ——这是「本字段对现有行为零影响」的保证。
2. **未注册的 kind 被拒绝**而不是静默回退到 pi。用户以为换了后端而实际没换，
   比直接报错难发现得多（会先归因于「新模型效果不行」）。
3. **契约双向可见**：SessionOut 回报 agent_kind，SessionIn 允许指定。
"""

from __future__ import annotations

import pytest

from apps.agent.backends import available_kinds, registry
from apps.agent.models import AgentSession
from apps.agent.schemas import SessionIn, SessionOut
from apps.agent.services.session_service import create_session

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


class TestModelDefault:
    def test_model_field_defaults_to_pi(self) -> None:
        field = AgentSession._meta.get_field("agent_kind")
        assert field.default == "pi"
        assert field.db_index is True  # 会话列表要按它筛选/展示

    def test_model_field_allows_blank_for_legacy_rows(self) -> None:
        # 历史行在迁移时被填成 pi，但允许 blank 让「未注水」的读取路径安全
        field = AgentSession._meta.get_field("agent_kind")
        assert field.blank is True


class TestCreateSession:
    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_default_agent_kind_is_pi(self) -> None:
        session = await create_session(title="t", user_id=None)
        assert session.agent_kind == "pi"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_empty_string_falls_back_to_pi(self) -> None:
        # 旧调用方（任务式 / 子任务 / 测试）不传或传空，行为必须与引入前一致
        session = await create_session(title="t", user_id=None, agent_kind="")
        assert session.agent_kind == "pi"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_explicit_kind_persisted(self) -> None:
        session = await create_session(title="t", user_id=None, agent_kind="pi")
        refreshed = await AgentSession.objects.aget(pk=session.pk)
        assert refreshed.agent_kind == "pi"


class TestSchemas:
    def test_session_out_exposes_agent_kind(self) -> None:
        # 前端要知道每条会话用的是哪个 agent（列表里显示标识）
        assert "agent_kind" in SessionOut.model_fields

    def test_session_in_accepts_agent_kind(self) -> None:
        # 与 llm_model 相反：agent 是用户的选择，必须可由客户端指定
        payload = SessionIn(agent_kind="pi")
        assert payload.agent_kind == "pi"

    def test_session_in_defaults_to_pi(self) -> None:
        assert SessionIn().agent_kind == "pi"


class TestRegistryContract:
    def test_available_kinds_returns_list(self) -> None:
        assert isinstance(available_kinds(), list)

    def test_unknown_kind_lookup_raises(self) -> None:
        # 创建接口靠这个判断是否放行；未注册必须报错而非静默回退
        with pytest.raises(LookupError):
            registry.get("__definitely_not_registered__")
