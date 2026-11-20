"""案件会话的「项目归属」（``AgentSession.contract_id``）推导与存量回填。

背景：``contract_id`` 是「这条会话属于哪个项目」的锚点——项目页按它拉会话、
侧栏按它分组、跨会话共享上下文（项目笔记）按它挂载。前端在案件页只发
``case_id``（``CopilotScope`` 是 case|contract 二选一），所以历史案件会话的
``contract_id`` 恒为 NULL。

四个验收点：

1. 案件会话建的时候**自动**带上案件的 ``contract_id``，不依赖客户端多传字段；
2. 显式传的 ``contract_id`` 不被覆盖（调用方意图优先）；
3. 案件没关联项目 / 案件不存在 / 非案件会话 → 保持为空，**不猜**；
4. 存量回填命令：幂等、``--dry-run`` 不写库、补不了的两类分别计数。
"""

from __future__ import annotations

from io import StringIO

import pytest
from asgiref.sync import async_to_sync
from django.core.management import call_command

from apps.agent.models import AgentSession
from apps.agent.services.session_service import create_session, resolve_contract_id
from apps.cases.models import Case
from apps.contracts.models import Contract


def _make_contract(name: str = "委托合同A") -> Contract:
    return Contract.objects.create(name=name, case_type="civil")


def _make_case(contract: Contract | None, name: str = "案件A") -> Case:
    return Case.objects.create(name=name, contract=contract)


class TestResolveContractId:
    @pytest.mark.django_db
    def test_case_with_contract_derives_it(self) -> None:
        contract = _make_contract()
        case = _make_case(contract)
        assert async_to_sync(resolve_contract_id)(case_id=case.pk, contract_id=None) == contract.pk

    @pytest.mark.django_db
    def test_explicit_contract_wins(self) -> None:
        contract_a = _make_contract("合同A")
        contract_b = _make_contract("合同B")
        case = _make_case(contract_a)
        resolved = async_to_sync(resolve_contract_id)(case_id=case.pk, contract_id=contract_b.pk)
        assert resolved == contract_b.pk

    @pytest.mark.django_db
    def test_case_without_contract_stays_none(self) -> None:
        # Case.contract 允许为空（历史/导入案件）：宁可项目维度缺一条，也不猜
        case = _make_case(None, "无项目案件")
        assert async_to_sync(resolve_contract_id)(case_id=case.pk, contract_id=None) is None

    @pytest.mark.django_db
    def test_missing_case_stays_none(self) -> None:
        assert async_to_sync(resolve_contract_id)(case_id=10**9, contract_id=None) is None

    @pytest.mark.django_db
    def test_no_case_keeps_contract(self) -> None:
        contract = _make_contract()
        assert async_to_sync(resolve_contract_id)(case_id=None, contract_id=contract.pk) == contract.pk


class TestCreateSession:
    @pytest.mark.django_db
    def test_case_session_carries_project(self) -> None:
        contract = _make_contract()
        case = _make_case(contract)
        session = async_to_sync(create_session)(title="t", user_id=None, origin="case", case_id=case.pk)
        assert session.contract_id == contract.pk
        assert session.case_id == case.pk

    @pytest.mark.django_db
    def test_chat_session_unaffected(self) -> None:
        session = async_to_sync(create_session)(title="t", user_id=None)
        assert session.case_id is None
        assert session.contract_id is None

    @pytest.mark.django_db
    def test_contract_session_unaffected(self) -> None:
        contract = _make_contract()
        session = async_to_sync(create_session)(
            title="t", user_id=None, origin="contract", contract_id=contract.pk
        )
        assert session.contract_id == contract.pk
        assert session.case_id is None


class TestBackfillCommand:
    @pytest.mark.django_db
    def test_fills_only_resolvable_sessions(self) -> None:
        contract = _make_contract()
        case = _make_case(contract)
        orphan_case = _make_case(None, "无项目案件")

        legacy = AgentSession.objects.create(title="a", origin="case", case_id=case.pk)
        blind = AgentSession.objects.create(title="b", origin="case", case_id=orphan_case.pk)
        ghost = AgentSession.objects.create(title="c", origin="case", case_id=10**9)

        out = StringIO()
        call_command("backfill_session_contract", stdout=out)

        legacy.refresh_from_db()
        blind.refresh_from_db()
        ghost.refresh_from_db()
        assert legacy.contract_id == contract.pk
        assert blind.contract_id is None
        assert ghost.contract_id is None

        text = out.getvalue()
        assert "可回填 1 条" in text
        # 两类「补不了」分别计数，而不是混成一个数字
        assert "案件未关联项目 1 条" in text
        assert "案件已不存在 1 条" in text

    @pytest.mark.django_db
    def test_dry_run_writes_nothing(self) -> None:
        contract = _make_contract()
        case = _make_case(contract)
        session = AgentSession.objects.create(title="a", origin="case", case_id=case.pk)

        out = StringIO()
        call_command("backfill_session_contract", "--dry-run", stdout=out)

        session.refresh_from_db()
        assert session.contract_id is None
        assert "[dry-run]" in out.getvalue()

    @pytest.mark.django_db
    def test_idempotent(self) -> None:
        contract = _make_contract()
        case = _make_case(contract)
        session = AgentSession.objects.create(title="a", origin="case", case_id=case.pk)

        call_command("backfill_session_contract", stdout=StringIO())
        out = StringIO()
        call_command("backfill_session_contract", stdout=out)

        session.refresh_from_db()
        assert session.contract_id == contract.pk
        assert "没有需要回填的会话" in out.getvalue()
