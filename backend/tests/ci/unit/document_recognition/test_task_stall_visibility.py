"""识别任务「卡住可见」机制的纯逻辑测试（2026-10-28 事故回归）。

事故：本机 Clash 把内网 LLM 网关当外网走代理，调用持续 502 重试，单次识别
实测 439 秒（llm_latency_ms=439725）。但接口只回 status=processing，前端无法
区分"还在正常跑"和"已经僵死"，界面全程只显示「识别中…通常 5-30 秒」。

修复是接口补三个字段：started_at / elapsed_seconds / stalled。这里只测
判定逻辑本身（不碰 DB、不碰 HTTP），因为它是"卡住可见"的唯一真相来源。
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

from apps.document_recognition.api.document_recognition_api import (
    STALLED_THRESHOLD_SECONDS,
    _elapsed_seconds,
    _is_stalled,
)


def _task(status: str, *, started_ago: int | None = None, finished_ago: int | None = None) -> SimpleNamespace:
    now = timezone.now()
    return SimpleNamespace(
        status=status,
        created_at=now - timedelta(seconds=(started_ago or 0) + 1),
        started_at=None if started_ago is None else now - timedelta(seconds=started_ago),
        finished_at=None if finished_ago is None else now - timedelta(seconds=finished_ago),
    )


class TestElapsedSeconds:
    def test_未开始计时时退回创建时间(self) -> None:
        # pending 任务还没被 worker 拉起：started_at 为空，仍应给出已排队时长
        elapsed = _elapsed_seconds(_task("pending", started_ago=None))
        assert elapsed is not None
        assert elapsed >= 0

    def test_进行中按当前时间滚动计算(self) -> None:
        elapsed = _elapsed_seconds(_task("processing", started_ago=120))
        assert elapsed is not None
        assert 118 <= elapsed <= 125

    def test_已结束用finished_at锁定不再增长(self) -> None:
        # 成功任务即使过了很久，耗时也必须停在 finished_at，不能随"现在"一直涨
        task = _task("success", started_ago=1000, finished_ago=970)
        elapsed = _elapsed_seconds(task)
        assert elapsed is not None
        assert 28 <= elapsed <= 32

    def test_无任何时间字段时返回None(self) -> None:
        assert _elapsed_seconds(SimpleNamespace(status="pending", created_at=None, started_at=None, finished_at=None)) is None


class TestIsStalled:
    def test_processing超过阈值判为僵死(self) -> None:
        assert _is_stalled(_task("processing", started_ago=STALLED_THRESHOLD_SECONDS + 10)) is True

    def test_processing未超阈值不算僵死(self) -> None:
        assert _is_stalled(_task("processing", started_ago=5)) is False

    def test_pending排队不算僵死(self) -> None:
        # 排队是正常状态，不能用它触发"可能卡住"的告警
        assert _is_stalled(_task("pending", started_ago=STALLED_THRESHOLD_SECONDS * 2)) is False

    def test_成功任务永不算僵死即使耗时很长(self) -> None:
        # 事故里那条任务耗时 439 秒但最终 success —— 成功就是成功，
        # 不能让前端把它渲染成"卡住了"并诱导用户重跑覆盖已确认数据
        assert _is_stalled(_task("success", started_ago=439, finished_ago=0)) is False

    def test_失败任务不算僵死(self) -> None:
        assert _is_stalled(_task("failed", started_ago=400, finished_ago=0)) is False

    def test_阈值是180秒(self) -> None:
        # 阈值本身也锁一下：改小会把正常慢识别误报成卡死，改大则失去预警意义
        assert STALLED_THRESHOLD_SECONDS == 180
