"""试跑的入账与日限流（``services/skills/trial_ledger.py``）。

这两件事的坑全在边界上：算的是本地自然日还是 UTC 日、并发双击会不会多算一次、
失败的那一轮算不算成本。它们都**不产生任何可见错误**——只会在某天早上被审批人
发现「明明是新的这一天，却说次数用完了」，或者账上永远只有成功的那几次。

``reserve`` 必须先落行（跑之前计数）：这样才能既挡住并发双击，也让超时/报错的
那一轮留下成本痕迹。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

import pytest
from django.db import connection
from django.utils import timezone

from apps.agent.models import AgentSkill, AgentSkillTrial
from apps.agent.services.skills import errors, trial_ledger
from apps.agent.services.skills.errors import SkillQuotaExceeded
from apps.organization.models import LawFirm, Lawyer

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


@pytest.fixture
def lawyer(db: Any) -> Lawyer:
    firm = LawFirm.objects.create(name="试跑账本所")
    return Lawyer.objects.create_user(username="trial-ledger", password=TEST_PASSWORD, law_firm=firm)


@pytest.fixture
def skill(lawyer: Lawyer) -> AgentSkill:
    return AgentSkill.objects.create(
        scope=AgentSkill.Scope.LAWYER,
        lawyer=lawyer,
        name="ledger-skill",
        title="账本技能",
        description="用于入账的试跑技能",
        body="按它做",
        created_by=lawyer,
    )


class TestDailyLimit:
    """上限口径：默认 30，env 可覆盖，非法值回落且不抛。"""

    def test_default_is_thirty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(trial_ledger.DAILY_LIMIT_ENV, raising=False)
        assert trial_ledger.daily_limit() == 30

    def test_blank_env_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(trial_ledger.DAILY_LIMIT_ENV, "   ")
        assert trial_ledger.daily_limit() == 30

    def test_env_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(trial_ledger.DAILY_LIMIT_ENV, " 7 ")
        assert trial_ledger.daily_limit() == 7

    @pytest.mark.parametrize("raw", ["abc", "0", "-3", "1.5", "30 次"])
    def test_invalid_env_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        """配错一个字不该把试跑按钮变成 500：回落默认值 + 告警（只喊一次）。"""
        monkeypatch.setenv(trial_ledger.DAILY_LIMIT_ENV, raw)
        assert trial_ledger.daily_limit() == 30


class TestUsage:
    def test_counts_only_my_own_rows(self, lawyer: Lawyer, skill: AgentSkill) -> None:
        other = Lawyer.objects.create_user(username="trial-ledger-other", password=TEST_PASSWORD, law_firm=lawyer.law_firm)
        trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")
        trial_ledger.reserve(user_id=other.pk, skill=skill, backend="pi", mode="inline")

        usage = trial_ledger.usage(lawyer.pk)

        assert usage["used"] == 1
        assert usage["remaining"] == trial_ledger.daily_limit() - 1

    def test_counts_a_row_before_it_finishes(self, lawyer: Lawyer, skill: AgentSkill) -> None:
        """跑之前就落行：这一条是「并发双击也计数」与「崩在中间不漏账」的共同前提。"""
        row = trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")

        assert row.ok is False
        assert trial_ledger.usage(lawyer.pk)["used"] == 1

    def test_yesterday_rows_do_not_count(self, lawyer: Lawyer, skill: AgentSkill) -> None:
        row = trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")
        AgentSkillTrial.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=1))

        assert trial_ledger.usage(lawyer.pk)["used"] == 0

    def test_remaining_is_clamped_at_zero(self, lawyer: Lawyer, skill: AgentSkill, monkeypatch: pytest.MonkeyPatch) -> None:
        """上限被调小、当天已经跑超：``remaining`` 不能是负数（前端进度条会破图）。"""
        monkeypatch.setenv(trial_ledger.DAILY_LIMIT_ENV, "5")
        for _ in range(3):
            trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")
        monkeypatch.setenv(trial_ledger.DAILY_LIMIT_ENV, "2")

        usage = trial_ledger.usage(lawyer.pk)

        assert (usage["limit"], usage["used"], usage["remaining"]) == (2, 3, 0)

    def test_reset_at_is_tomorrow_local_midnight(self, lawyer: Lawyer) -> None:
        """恢复时刻必须是**明日本地零点**：与「本地自然日」计数口径同源。"""
        expected = datetime.combine(
            timezone.localdate() + timedelta(days=1), time.min, tzinfo=timezone.get_current_timezone()
        )

        reset_at = datetime.fromisoformat(trial_ledger.usage(lawyer.pk)["reset_at"])

        assert reset_at == expected
        assert reset_at.utcoffset() is not None, "必须带时区，前端不该猜服务端在哪个时区"


class TestReserve:
    def test_writes_a_row_before_the_run(self, lawyer: Lawyer, skill: AgentSkill) -> None:
        row = trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="index")

        assert row.pk is not None
        assert row.skill_key == f"skill:{skill.pk}"
        assert row.backend == "pi"
        assert row.mode == "index"
        assert (row.ok, row.duration_ms, row.response_chars, row.tool_calls_count) == (False, 0, 0, 0)

    def test_raises_when_today_is_exhausted(self, lawyer: Lawyer, skill: AgentSkill, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(trial_ledger.DAILY_LIMIT_ENV, "1")
        trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")

        with pytest.raises(SkillQuotaExceeded) as excinfo:
            trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")

        message = str(excinfo.value)
        assert "今日试跑次数已用完" in message
        assert "1 次/天" in message
        assert "后恢复" in message

    def test_reuses_the_shared_quota_error(self) -> None:
        """超限**复用** ``errors.SkillQuotaExceeded``：API 层的 429 映射只认这一个类，
        新造一个异常类会让超限变成 500。"""
        assert trial_ledger.SkillQuotaExceeded is errors.SkillQuotaExceeded

    def test_skill_key_survives_skill_deletion(self, lawyer: Lawyer, skill: AgentSkill) -> None:
        """技能被删后流水必须还在：``skill`` 置空，但 ``skill_key`` 保留当时试的是谁。"""
        skill_key = f"skill:{skill.pk}"
        row = trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")

        skill.delete()
        row.refresh_from_db()

        assert row.skill_id is None
        assert row.skill_key == skill_key


@pytest.mark.django_db(transaction=True)
class TestReserveConcurrency:
    """并发双击「试跑」：日限必须真的守住（照 ``user_skills._lock_quota`` 的咨询锁）。

    没有锁时两个请求都读到 ``used=limit-1`` 然后各落一行——多算一次不会报错，
    只会让审批人某天少了一次机会，且没人能复现。
    """

    def test_concurrent_reserve_stops_at_limit(
        self, lawyer: Lawyer, skill: AgentSkill, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import threading

        if connection.vendor != "postgresql":
            pytest.skip("advisory lock 只在 PostgreSQL 上生效（本地 sqlite 跳过）")
        monkeypatch.setenv(trial_ledger.DAILY_LIMIT_ENV, "3")
        threads_count = 8
        barrier = threading.Barrier(threads_count)
        created: list[str] = []
        rejections: list[str] = []
        guard = threading.Lock()

        def _attempt() -> None:
            barrier.wait()
            try:
                row = trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")
            except SkillQuotaExceeded as exc:
                with guard:
                    rejections.append(str(exc))
            else:
                with guard:
                    created.append(str(row.pk))
            finally:
                connection.close()

        threads = [threading.Thread(target=_attempt) for _ in range(threads_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(created) == 3
        assert len(rejections) == threads_count - 3
        assert AgentSkillTrial.objects.filter(user_id=lawyer.pk).count() == 3


class TestFinish:
    def test_fills_the_row(self, lawyer: Lawyer, skill: AgentSkill) -> None:
        row = trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")

        trial_ledger.finish(
            row, ok=True, duration_ms=1234, response_chars=56, tool_calls_count=2, error="", model="gpt-x"
        )
        row.refresh_from_db()

        assert (row.ok, row.duration_ms, row.response_chars, row.tool_calls_count) == (True, 1234, 56, 2)
        assert row.model == "gpt-x"

    def test_records_failure_too(self, lawyer: Lawyer, skill: AgentSkill) -> None:
        """失败也要回填（ok=False + 原因）：那一轮同样起了进程、烧了一次模型调用。"""
        row = trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")

        trial_ledger.finish(
            row, ok=False, duration_ms=900, response_chars=0, tool_calls_count=0, error="模型通道 429", model=None
        )
        row.refresh_from_db()

        assert row.ok is False
        assert row.error == "模型通道 429"
        assert row.duration_ms == 900
        assert row.model == ""

    def test_truncates_error_to_field_width(self, lawyer: Lawyer, skill: AgentSkill) -> None:
        """``error`` 只留原因、且按字段宽度截断：回复正文不该被塞进这一列。"""
        row = trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")

        trial_ledger.finish(
            row, ok=False, duration_ms=0, response_chars=0, tool_calls_count=0, error="错" * 500, model="m" * 300
        )
        row.refresh_from_db()

        assert len(row.error) == AgentSkillTrial.ERROR_MAX_CHARS == 200
        assert len(row.model) == trial_ledger.MODEL_MAX_CHARS == 100

    def test_clamps_negative_numbers(self, lawyer: Lawyer, skill: AgentSkill) -> None:
        """三个计数字段是正整数字段：负数在 PostgreSQL 上会直接抛，先在服务层夹住。"""
        row = trial_ledger.reserve(user_id=lawyer.pk, skill=skill, backend="pi", mode="inline")

        trial_ledger.finish(row, ok=False, duration_ms=-5, response_chars=-1, tool_calls_count=-2, error="x", model="m")
        row.refresh_from_db()

        assert (row.duration_ms, row.response_chars, row.tool_calls_count) == (0, 0, 0)
