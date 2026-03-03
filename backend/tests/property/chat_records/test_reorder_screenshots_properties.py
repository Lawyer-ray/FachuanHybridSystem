"""
Property-Based Tests for reorder_screenshots Batch Update Correctness

# Feature: chat-records-quality-uplift, Property 4: reorder_screenshots 批量更新正确性

**Validates: Requirements 9.1, 9.2**

对任意项目及其关联的 N 张截图（含不同 capture_time_seconds 和 created_at），
执行 reorder_by_capture_time 后：
(a) 所有截图的 ordering 值为 1 到 N 的连续整数；
(b) 按 capture_time_seconds 升序（NULL 排最后）、created_at 升序排列；
(c) 整个操作执行不超过 2 次数据库查询。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.chat_records.models import ChatRecordProject, ChatRecordScreenshot, ScreenshotSource
from apps.chat_records.services.screenshot_service import ScreenshotService

# ========== Strategies ==========

# 截图条目：capture_time_seconds 可为 None（NULL last）或正浮点数
screenshot_entry_st = st.fixed_dictionaries(
    {
        "capture_time_seconds": st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=36000.0, allow_nan=False, allow_infinity=False),
        ),
        "created_at_offset_seconds": st.integers(min_value=0, max_value=86400),
    }
)

# 生成 1~20 张截图的列表
screenshot_list_st = st.lists(screenshot_entry_st, min_size=1, max_size=20)


# ========== Fixtures ==========


@pytest.fixture()
def project(db: Any) -> ChatRecordProject:
    """创建测试项目。"""
    proj: ChatRecordProject = ChatRecordProject.objects.create(name="排序测试项目")
    return proj


# ========== Property Tests ==========


@pytest.mark.django_db
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entries=screenshot_list_st)
def test_reorder_by_capture_time_correctness(
    project: ChatRecordProject,
    assert_num_queries: Any,
    entries: list[dict[str, Any]],
) -> None:
    """
    # Feature: chat-records-quality-uplift, Property 4: reorder_screenshots 批量更新正确性

    **Validates: Requirements 9.1, 9.2**
    """
    # -- Arrange: 清理旧数据，创建新截图 --
    ChatRecordScreenshot.objects.filter(project=project).delete()

    base_time = timezone.now()
    for i, entry in enumerate(entries):
        ChatRecordScreenshot.objects.create(
            project=project,
            image=f"fake/img_{i}.png",
            ordering=0,
            capture_time_seconds=entry["capture_time_seconds"],
            source=ScreenshotSource.EXTRACT,
            created_at=base_time + timedelta(seconds=entry["created_at_offset_seconds"]),
        )

    n = len(entries)
    service = ScreenshotService.__new__(ScreenshotService)

    # -- Act: 执行批量重排序，验证查询次数 ≤ 2 --
    with assert_num_queries(2):
        service.reorder_by_capture_time(project.id)

    # -- Assert (a): ordering 值为 1..N 连续整数 --
    screenshots = list(ChatRecordScreenshot.objects.filter(project=project).order_by("ordering"))
    assert len(screenshots) == n
    orderings = [s.ordering for s in screenshots]
    assert orderings == list(range(1, n + 1))

    # -- Assert (b): 按 capture_time_seconds ASC (NULL last), created_at ASC --
    for i in range(len(screenshots) - 1):
        curr = screenshots[i]
        nxt = screenshots[i + 1]

        curr_cts = curr.capture_time_seconds
        nxt_cts = nxt.capture_time_seconds

        # NULL 排最后
        if curr_cts is None and nxt_cts is not None:
            raise AssertionError(
                f"ordering {curr.ordering}: capture_time_seconds=NULL 应排在 "
                f"ordering {nxt.ordering}: capture_time_seconds={nxt_cts} 之后"
            )

        # 两者都非 NULL 时，按 capture_time_seconds 升序
        if curr_cts is not None and nxt_cts is not None:
            if curr_cts > nxt_cts:
                raise AssertionError(
                    f"ordering {curr.ordering}: cts={curr_cts} > ordering {nxt.ordering}: cts={nxt_cts}"
                )
            # capture_time_seconds 相同时，按 created_at 升序
            if curr_cts == nxt_cts and curr.created_at > nxt.created_at:
                raise AssertionError(
                    f"ordering {curr.ordering}: same cts={curr_cts}, "
                    f"but created_at {curr.created_at} > {nxt.created_at}"
                )

        # 两者都为 NULL 时，按 created_at 升序
        if curr_cts is None and nxt_cts is None:
            if curr.created_at > nxt.created_at:
                raise AssertionError(
                    f"ordering {curr.ordering}: both NULL cts, but created_at {curr.created_at} > {nxt.created_at}"
                )
