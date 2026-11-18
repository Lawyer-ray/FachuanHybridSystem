"""执行位预算（services/chat/budget.py）单测。

锁两件事：
1. primary 用途**完全不受限**——这是「引入本模块对现有行为零影响」的保证，
   一旦这条破了，正常提问会被新加的限流挡住。
2. aux 用途满额时**立即失败**而不是排队——对比/审校是增强能力，
   卡住等 60 秒比直接降级体验差得多。
"""

from __future__ import annotations

import pytest

from apps.agent.services.chat import budget


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch):
    """每个用例前清空计数与相关环境变量，避免相互污染。"""
    budget._budget.reset()
    monkeypatch.delenv("FACHUAN_AGENT_POOL_SIZE", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    yield
    budget._budget.reset()


class TestPrimaryIsUnlimited:
    """primary 必须与引入本模块前行为完全一致。"""

    @pytest.mark.asyncio
    async def test_many_primary_reservations_never_blocked(self) -> None:
        # 远超任何 aux 配额，仍应全部通过
        entered = 0
        for _ in range(100):
            async with budget.reserve("primary"):
                entered += 1
        # 显式断言而不是「没抛异常就算过」：后者在 reserve 被改成
        # 静默跳过时也会绿（本仓质量门禁禁止零断言用例）
        assert entered == 100

    @pytest.mark.asyncio
    async def test_primary_not_counted_in_aux_usage(self) -> None:
        async with budget.reserve("primary"):
            assert budget._budget.aux_in_use == 0

    @pytest.mark.asyncio
    async def test_primary_still_works_when_aux_exhausted(self) -> None:
        # aux 占满也不应影响 primary
        limit = budget.aux_slots()
        if limit == 0:
            pytest.skip("当前配置 aux 席为 0")
        ctxs = [budget.reserve("aux") for _ in range(limit)]
        for ctx in ctxs:
            await ctx.__aenter__()
        try:
            async with budget.reserve("primary"):
                pass
        finally:
            for ctx in ctxs:
                await ctx.__aexit__(None, None, None)


class TestAuxQuota:
    @pytest.mark.asyncio
    async def test_aux_rejects_immediately_when_full(self) -> None:
        limit = budget.aux_slots()
        if limit == 0:
            pytest.skip("当前配置 aux 席为 0")

        held = []
        for _ in range(limit):
            ctx = budget.reserve("aux")
            await ctx.__aenter__()
            held.append(ctx)

        try:
            # 满额后立刻抛，不等超时
            with pytest.raises(budget.BudgetExceeded):
                async with budget.reserve("aux"):
                    pass
        finally:
            for ctx in held:
                await ctx.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_aux_released_after_exit(self) -> None:
        limit = budget.aux_slots()
        if limit == 0:
            pytest.skip("当前配置 aux 席为 0")

        async with budget.reserve("aux"):
            assert budget._budget.aux_in_use == 1
        assert budget._budget.aux_in_use == 0

    @pytest.mark.asyncio
    async def test_aux_released_even_on_exception(self) -> None:
        with pytest.raises(ValueError):
            async with budget.reserve("aux"):
                raise ValueError("boom")
        assert budget._budget.aux_in_use == 0

    @pytest.mark.asyncio
    async def test_aux_zero_slots_always_degrades(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_AUX_SLOTS", "0")
        with pytest.raises(budget.BudgetExceeded, match="已关闭"):
            async with budget.reserve("aux"):
                pass


class TestSlotResolution:
    def test_default_total_is_four(self) -> None:
        assert budget._total_slots() == 4

    def test_total_clamped_to_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_POOL_SIZE", "999")
        assert budget._total_slots() == 32

    def test_total_garbage_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_POOL_SIZE", "abc")
        assert budget._total_slots() == 4

    def test_aux_ratio_default(self) -> None:
        # 4 * 0.25 = 1
        assert budget.aux_slots(4) == 1

    def test_aux_explicit_slots_override_ratio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_AUX_SLOTS", "2")
        assert budget.aux_slots(8) == 2

    def test_aux_slots_clamped_to_total(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_AUX_SLOTS", "99")
        assert budget.aux_slots(4) == 4

    def test_aux_ratio_zero_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_AUX_RATIO", "0")
        assert budget.aux_slots(8) == 0

    def test_aux_ratio_garbage_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_AUX_RATIO", "not-a-number")
        assert budget.aux_slots(4) == 1

    def test_total_one_gives_aux_zero(self) -> None:
        # 只有一个执行位时必须留给主答，否则主答反而排队
        assert budget.aux_slots(1) == 0

    def test_aux_never_takes_all_slots(self) -> None:
        # 无论比例多大，至少给主答留 1 席
        assert budget.aux_slots(4) < 4


class TestSnapshot:
    def test_snapshot_shape(self) -> None:
        snap = budget.snapshot()
        assert set(snap) == {"total_slots", "aux_slots", "aux_in_use", "primary_slots"}
        assert snap["primary_slots"] == snap["total_slots"] - snap["aux_slots"]

    @pytest.mark.asyncio
    async def test_snapshot_reflects_usage(self) -> None:
        limit = budget.aux_slots()
        if limit == 0:
            pytest.skip("当前配置 aux 席为 0")
        async with budget.reserve("aux"):
            assert budget.snapshot()["aux_in_use"] == 1
