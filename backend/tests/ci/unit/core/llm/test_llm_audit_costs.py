"""LLM 审计:版本标记与成本聚合单元测试。"""

from __future__ import annotations

import pytest

from apps.core.llm.costs import aaggregate_costs, aggregate_costs, estimate_cost, price_for_model


class TestPriceForModel:
    def test_exact_match(self):
        assert price_for_model("gpt-4o") == (2.50, 10.00)

    def test_prefix_match(self):
        assert price_for_model("gpt-4o-2024-05-13") == (2.50, 10.00)

    def test_substring_match(self):
        assert price_for_model("vllm/deepseek-chat") == (0.27, 1.10)

    def test_unknown_falls_back_to_default(self):
        assert price_for_model("custom-model") == (0.0, 0.0)

    def test_empty_model(self):
        assert price_for_model("") == (0.0, 0.0)

    def test_custom_pricing(self):
        custom = {"my-model": (1.0, 2.0)}
        assert price_for_model("my-model", pricing=custom) == (1.0, 2.0)


class TestEstimateCost:
    def test_computes_cost(self):
        # gpt-4o: 输入 2.5/1M, 输出 10/1M
        cost = estimate_cost(model="gpt-4o", prompt_tokens=1_000_000, completion_tokens=500_000)
        assert cost == pytest.approx(2.5 + 5.0)

    def test_zero_tokens_zero_cost(self):
        assert estimate_cost(model="unknown", prompt_tokens=0, completion_tokens=0) == 0.0


class TestAggregateCosts:
    @pytest.mark.django_db
    def test_aggregates_by_model_with_cost(self):
        from apps.core.models import LLMCallRecord

        LLMCallRecord.objects.create(
            model="gpt-4o",
            backend="openai_compatible",
            caller="a",
            success=True,
            prompt_tokens=1_000_000,
            completion_tokens=0,
            total_tokens=1_000_000,
            duration_ms=100,
        )
        LLMCallRecord.objects.create(
            model="gpt-4o",
            backend="openai_compatible",
            caller="a",
            success=True,
            prompt_tokens=0,
            completion_tokens=500_000,
            total_tokens=500_000,
            duration_ms=200,
        )
        LLMCallRecord.objects.create(
            model="deepseek-chat",
            backend="openai_compatible",
            caller="b",
            success=True,
            prompt_tokens=0,
            completion_tokens=1_000_000,
            total_tokens=1_000_000,
            duration_ms=50,
        )
        # 失败记录不计入聚合
        LLMCallRecord.objects.create(
            model="gpt-4o",
            backend="openai_compatible",
            caller="a",
            success=False,
            prompt_tokens=100,
            completion_tokens=10,
            total_tokens=110,
            duration_ms=1,
        )

        rows = aggregate_costs(group_by=("backend", "model"))
        by_model = {r["model"]: r for r in rows}

        gpt = by_model["gpt-4o"]
        assert gpt["call_count"] == 2
        assert gpt["sum_prompt_tokens"] == 1_000_000
        assert gpt["sum_completion_tokens"] == 500_000
        assert gpt["sum_total_tokens"] == 1_500_000
        # 2.5 (输入1M) + 5.0 (输出0.5M)
        assert gpt["estimated_cost_usd"] == pytest.approx(7.5)

        ds = by_model["deepseek-chat"]
        assert ds["call_count"] == 1
        # deepseek-chat 输出 1.10/1M
        assert ds["estimated_cost_usd"] == pytest.approx(1.1)

    @pytest.mark.django_db
    def test_filters_and_custom_pricing(self):
        from apps.core.models import LLMCallRecord

        LLMCallRecord.objects.create(
            model="m",
            backend="b1",
            caller="c",
            success=True,
            prompt_tokens=1_000_000,
            completion_tokens=0,
            total_tokens=1_000_000,
            duration_ms=1,
        )
        rows = aggregate_costs(group_by=("backend", "model"), caller="c", pricing={"m": (3.0, 0.0)})
        assert rows[0]["estimated_cost_usd"] == pytest.approx(3.0)

        rows2 = aggregate_costs(group_by=("backend", "model"), caller="nope")
        assert rows2 == []

        # 失败成功过滤
        LLMCallRecord.objects.create(
            model="m",
            backend="b1",
            caller="c",
            success=False,
            prompt_tokens=1_000_000,
            completion_tokens=0,
            total_tokens=1_000_000,
            duration_ms=1,
        )
        rows3 = aggregate_costs(group_by=("backend", "model"), caller="c")
        assert rows3[0]["call_count"] == 1  # 只算成功

    @pytest.mark.django_db(transaction=True)
    def test_async_aggregate(self):
        import asyncio

        from apps.core.models import LLMCallRecord

        LLMCallRecord.objects.create(
            model="gpt-4o",
            backend="b",
            caller="x",
            success=True,
            prompt_tokens=1_000_000,
            completion_tokens=0,
            total_tokens=1_000_000,
            duration_ms=1,
        )

        rows = asyncio.run(aaggregate_costs(group_by=("backend", "model")))
        assert rows and rows[0]["model"] == "gpt-4o"
        assert rows[0]["estimated_cost_usd"] == pytest.approx(2.5)


class TestVersionMarker:
    @pytest.mark.django_db
    def test_sync_record_writes_version(self):
        from apps.core.llm.tracking import AUDIT_VERSION, record_llm_call

        record_llm_call(backend="b", model="m", duration_ms=10, caller="test", prompt_tokens=1, completion_tokens=1)
        assert record_llm_call is not None
        from apps.core.models import LLMCallRecord

        rec = LLMCallRecord.objects.latest("id")
        assert rec.version == AUDIT_VERSION

    @pytest.mark.django_db
    def test_async_record_writes_version(self):
        import asyncio

        from apps.core.llm.tracking import AUDIT_VERSION, arecord_llm_call

        asyncio.run(arecord_llm_call(backend="b", model="m", duration_ms=10, caller="test"))
        from apps.core.models import LLMCallRecord

        rec = LLMCallRecord.objects.latest("id")
        assert rec.version == AUDIT_VERSION
