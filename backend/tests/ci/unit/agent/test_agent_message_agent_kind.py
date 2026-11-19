"""``AgentMessage.agent_kind``（消息级来源标注）与迁移 0017。

四个验收点：

1. **字段形状**：32 字符、带索引、``blank=True``、默认空串——索引是会话回放
   按它筛的前提，``blank`` 让未注水的读取路径安全；
2. **默认空串不是 ``pi``**：空串如实表示「旧数据 / 未标注」，回填成 pi 是猜；
3. **迁移 0017 已就位**：名字与依赖都对着的，不能被别的迁移抢了位次；
4. **契约可见**：``MessageOut`` 带上它，前端才能分栏渲染历史。

数据库层的行为（同一轮两条 assistant 各带 kind）在 ``test_dual_stream.py`` 里
端到端验过，这里只锁字段与迁移本身。
"""

from __future__ import annotations

import pytest

from apps.agent.models import AgentMessage
from apps.agent.schemas import MessageOut


class TestModelField:
    def test_shape(self) -> None:
        field = AgentMessage._meta.get_field("agent_kind")
        # db_index：历史回放/按栏过滤都要按它筛
        assert field.db_index is True
        # blank：让「未标注」的行在 admin / 序列化里不报错
        assert field.blank is True
        assert field.max_length == 32

    def test_default_is_empty_string_not_pi(self) -> None:
        # 空串 = 旧数据 / 未标注。填 'pi' 是把猜测固化成事实：引入本字段之前的
        # 会话也可能由别的入口产生，将来接更多后端时无法回头区分。
        field = AgentMessage._meta.get_field("agent_kind")
        assert field.default == ""

    @pytest.mark.django_db
    def test_new_message_defaults_to_blank(self) -> None:
        from apps.agent.models import AgentSession

        session = AgentSession.objects.create(title="t")
        message = AgentMessage.objects.create(session=session, role=AgentMessage.Role.ASSISTANT, content="答")
        message.refresh_from_db()
        assert message.agent_kind == ""


class TestMigration:
    def test_migration_0017_exists_and_depends_on_0016(self) -> None:
        from importlib import import_module

        module = import_module("apps.agent.migrations.0017_agent_message_agent_kind")
        assert module.Migration.dependencies == [("agent", "0016_agent_session_agent_kind")]

    def test_migration_adds_field_on_agentmessage(self) -> None:
        from importlib import import_module

        from django.db.migrations import AddField

        module = import_module("apps.agent.migrations.0017_agent_message_agent_kind")
        operations = [op for op in module.Migration.operations if isinstance(op, AddField)]
        assert len(operations) == 1
        assert operations[0].model_name == "agentmessage"
        assert operations[0].name == "agent_kind"

    def test_0017_is_ancestor_of_leaf(self) -> None:
        """0017 必须**排在**叶子之前（防孤儿迁移），而不是「自己就是叶子」。

        ## 为什么不能断言「叶子就是 0017」

        原先写的是 ``assert "0017..." in leaves``，本意是防「新迁移从更早的分支
        跳过了它」这个孤儿迁移的经典成因。但那个写法把「0017 是最后一个迁移」也
        一并锁死了——加 0018 时它就失败，而 0018 **正确地**依赖 0017 时没有任何
        问题。测试锁错了东西：要防的是「0017 被绕过」，不是「0017 后不能再加」。

        ## 改成沿依赖链往回走

        只要叶子能顺着 ``parent`` 回溯到 0017，就说明没有迁移跳过它；序数本身
        与「以后还会加多少迁移」解耦。

        不打 django_db：只要迁移图的**文件名与依赖**，不连数据库。
        """
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(None, ignore_no_migrations=True)
        leaves = [name for app, name in loader.graph.leaf_nodes() if app == "agent"]
        assert leaves, "agent 应用应有至少一个叶子迁移"

        target = "0017_agent_message_agent_kind"
        for leaf in leaves:
            # forwards_plan 返回到达该叶子的**完整迁移顺序**（含 0017 本身）。
            # 0017 在其中 = 没被绕过；用「在不在序列里」而不是「是不是最后」，
            # 这样再加 0019/0020 都不会误报。
            plan = [name for _app, name in loader.graph.forwards_plan(("agent", leaf))]
            assert target in plan, (
                f"叶子迁移 {leaf} 的依赖链里没有 {target} —— 0017 被绕过了"
                "（孤儿迁移：新迁移从更早的分支接出去，会导致 0017 的字段在某些库上缺失）"
                f"；实际链路：{plan}"
            )


class TestSchemaContract:
    def test_message_out_exposes_agent_kind(self) -> None:
        # 历史回放要能分栏：接口不带这个字段，前端就只能把两栏混成一段
        assert "agent_kind" in MessageOut.model_fields

    def test_message_out_defaults_to_blank_for_legacy_rows(self) -> None:
        out = MessageOut(message_id=1, role="assistant", content="答", tool_name="", created_at="")
        assert out.agent_kind == ""
