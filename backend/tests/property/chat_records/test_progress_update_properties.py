"""
Property-Based Tests for Progress Update Single DB Operation

# Feature: chat-records-quality-uplift, Property 1: 进度更新单次数据库操作

**Validates: Requirements 1.4**

对任意合法的进度更新参数组合，调用 update_export_progress 或
update_extract_progress 时，应在不超过 1 次数据库 UPDATE 操作中完成所有字段的更新。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.chat_records.models import (
    ChatRecordExportTask,
    ChatRecordProject,
    ChatRecordRecording,
    ExportStatus,
    ExportType,
    ExtractStatus,
)
from apps.chat_records.services.export_task_service import ExportTaskService
from apps.chat_records.services.recording_extract_facade import RecordingExtractFacade

# ========== Strategies ==========

status_export_st = st.sampled_from([s.value for s in ExportStatus])
status_extract_st = st.sampled_from([s.value for s in ExtractStatus])
progress_st = st.integers(min_value=0, max_value=100)
count_st = st.integers(min_value=0, max_value=10000)
message_st = st.text(min_size=0, max_size=200, alphabet=st.characters(categories=("L", "N", "Z")))
error_st = st.text(min_size=0, max_size=200, alphabet=st.characters(categories=("L", "N", "Z")))


# ========== Fixtures ==========


@pytest.fixture()
def project(db: Any) -> ChatRecordProject:
    """创建测试项目（不需要 created_by）。"""
    proj: ChatRecordProject = ChatRecordProject.objects.create(name="测试项目")
    return proj


@pytest.fixture()
def export_task(project: ChatRecordProject) -> ChatRecordExportTask:
    """创建测试导出任务。"""
    task: ChatRecordExportTask = ChatRecordExportTask.objects.create(
        project=project,
        export_type=ExportType.PDF,
        status=ExportStatus.RUNNING,
    )
    return task


@pytest.fixture()
def recording(project: ChatRecordProject) -> ChatRecordRecording:
    """创建测试录屏记录。"""
    rec: ChatRecordRecording = ChatRecordRecording.objects.create(
        project=project,
        video="fake/video.mp4",
        original_name="test.mp4",
        extract_status=ExtractStatus.RUNNING,
    )
    return rec


@pytest.fixture()
def export_service() -> ExportTaskService:
    """构造 ExportTaskService（update_export_progress 不依赖注入的服务）。"""
    mock_task_sub: Any = MagicMock()
    mock_proj_svc: Any = MagicMock()
    return ExportTaskService(
        task_submission_service=mock_task_sub,
        project_service=mock_proj_svc,
    )


@pytest.fixture()
def extract_facade() -> RecordingExtractFacade:
    """构造 RecordingExtractFacade（update_extract_progress 不依赖注入的服务）。"""
    mock_task_sub: Any = MagicMock()
    return RecordingExtractFacade(task_submission_service=mock_task_sub)


# ========== Property Tests ==========


@pytest.mark.django_db
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    status=st.one_of(st.none(), status_export_st),
    progress=st.one_of(st.none(), progress_st),
    current=st.one_of(st.none(), count_st),
    total=st.one_of(st.none(), count_st),
    message=message_st,
    error=error_st,
)
def test_export_progress_single_query(
    export_task: ChatRecordExportTask,
    export_service: ExportTaskService,
    assert_num_queries: Any,
    status: str | None,
    progress: int | None,
    current: int | None,
    total: int | None,
    message: str,
    error: str,
) -> None:
    """
    # Feature: chat-records-quality-uplift, Property 1: 进度更新单次数据库操作

    对任意合法的进度参数组合，update_export_progress 应在 1 次 UPDATE 中完成。
    **Validates: Requirements 1.4**
    """
    with assert_num_queries(1):
        export_service.update_export_progress(
            task_id=str(export_task.id),
            status=status,
            progress=progress,
            current=current,
            total=total,
            message=message,
            error=error,
        )


@pytest.mark.django_db
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    status=st.one_of(st.none(), status_extract_st),
    progress=st.one_of(st.none(), progress_st),
    current=st.one_of(st.none(), count_st),
    total=st.one_of(st.none(), count_st),
    message=message_st,
    error=error_st,
    duration_seconds=st.one_of(st.none(), st.floats(min_value=0.0, max_value=86400.0)),
)
def test_extract_progress_single_query(
    recording: ChatRecordRecording,
    extract_facade: RecordingExtractFacade,
    assert_num_queries: Any,
    status: str | None,
    progress: int | None,
    current: int | None,
    total: int | None,
    message: str,
    error: str,
    duration_seconds: float | None,
) -> None:
    """
    # Feature: chat-records-quality-uplift, Property 1: 进度更新单次数据库操作

    对任意合法的进度参数组合，update_extract_progress 应在 1 次 UPDATE 中完成。
    **Validates: Requirements 1.4**
    """
    with assert_num_queries(1):
        extract_facade.update_extract_progress(
            recording_id=str(recording.id),
            status=status,
            progress=progress,
            current=current,
            total=total,
            message=message,
            error=error,
            duration_seconds=duration_seconds,
        )
