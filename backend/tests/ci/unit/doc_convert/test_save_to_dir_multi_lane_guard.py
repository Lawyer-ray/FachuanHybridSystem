"""`/doc-converter/jobs/{job_id}/save-to-dir` 的多栏兜底（入口 C）。

save-to-dir 把转换产物**写进用户指定的目录**，是这条链路里唯一的写盘动作。
多栏并答时 agent 调它，同样是「替其它栏落盘」。三条口径：

1. 带会话头 + 该会话多栏登记 → 409，且落盘服务一次都没被调用；
2. 带会话头 + 单栏 → 正常保存；
3. 不带会话头（律师在页面上点「保存到目录」）→ 正常保存。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from django.test import RequestFactory

import apps.doc_converter.api.doc_converter_api as api
from apps.agent.services.approval.policy import clear_multi_lane_session, mark_multi_lane_session
from apps.agent.services.approval.write_guard import MULTI_LANE_WRITE_CODE
from apps.core.exceptions import ConflictError
from apps.doc_converter.schemas import SaveToDirIn

MULTI = "doc-convert-multi-lane"
SINGLE = "doc-convert-single-lane"
SAVED = {"saved_files": ["/tmp/out/a.docx"], "total_saved": 1, "target_dir": "/tmp/out"}


def _request(session_id: str | None) -> Any:
    headers = {"x-fachuan-session": session_id} if session_id else {}
    return RequestFactory().post("/doc-converter/jobs/x/save-to-dir", headers=headers)


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.get_job.return_value = MagicMock()
    fake.save_job_to_directory.return_value = dict(SAVED)
    monkeypatch.setattr(api, "_service", fake)
    return fake


@pytest.fixture
def multi_session() -> Any:
    mark_multi_lane_session(MULTI)
    try:
        yield MULTI
    finally:
        clear_multi_lane_session(MULTI)


@pytest.fixture
def single_session() -> Any:
    mark_multi_lane_session(SINGLE)
    clear_multi_lane_session(SINGLE)
    return SINGLE


def _call(session_id: str | None) -> Any:
    return api.save_to_directory(_request(session_id), job_id=uuid4(), payload=SaveToDirIn(target_dir="/tmp/out"))


class TestSaveToDirectoryMultiLaneGuard:
    def test_multi_lane_agent_is_refused_before_writing(self, service: MagicMock, multi_session: str) -> None:
        with pytest.raises(ConflictError) as exc_info:
            _call(multi_session)

        assert exc_info.value.code == MULTI_LANE_WRITE_CODE
        assert "propose_write_patch" in str(exc_info.value.message)
        assert exc_info.value.errors["endpoint"] == "doc_converter.save_to_dir"
        service.save_job_to_directory.assert_not_called()

    def test_single_lane_agent_still_saves(self, service: MagicMock, single_session: str) -> None:
        result = _call(single_session)

        assert result["total_saved"] == 1
        service.save_job_to_directory.assert_called_once()

    def test_lawyer_without_header_still_saves(self, service: MagicMock, multi_session: str) -> None:
        """页面上点「保存到目录」没有会话头：别的会话多栏并答不影响律师本人操作。"""
        result = _call(None)

        assert result["target_dir"] == "/tmp/out"
        service.save_job_to_directory.assert_called_once()
