"""mock_trial/report_service.py 单元测试（仓储层 mock）.

覆盖 get_report 三种模式分发、judge/cross_exam/debate 报告聚合逻辑、
保存类方法的元数据写入。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService


@pytest.fixture()
def mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_metadata = AsyncMock(return_value={})
    repo.update_metadata = AsyncMock()
    with patch(
        "apps.litigation_ai.services.flow.session_repository.LitigationSessionRepository",
        return_value=repo,
    ):
        yield repo


class TestGetReportDispatch:
    @pytest.mark.asyncio
    async def test_judge_mode(self, mock_repo: MagicMock) -> None:
        mock_repo.get_metadata.return_value = {
            "mock_trial_mode": "judge",
            "report": {"风险": "高"},
            "report_model": "gpt-x",
            "report_token_usage": {"input": 10},
            "judge_report_saved_at": "2026-01-01T00:00:00",
        }
        result = await MockTrialReportService().get_report("s1")
        assert result["mode"] == "judge"
        assert result["status"] == "complete"
        assert result["report"] == {"风险": "高"}
        assert result["model"] == "gpt-x"
        assert result["token_usage"] == {"input": 10}
        assert result["saved_at"] == "2026-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_judge_mode_no_data(self, mock_repo: MagicMock) -> None:
        mock_repo.get_metadata.return_value = {"mock_trial_mode": "judge"}
        result = await MockTrialReportService().get_report("s1")
        assert result["status"] == "no_data"
        assert result["report"] == {}
        assert result["model"] == ""

    @pytest.mark.asyncio
    async def test_cross_exam_mode(self, mock_repo: MagicMock) -> None:
        mock_repo.get_metadata.return_value = {
            "mock_trial_mode": "cross_exam",
            "cross_exam_results": [
                {"evidence_name": "借条", "opinion": {"risk_level": "high"}},
                {"evidence_name": "合同", "opinion": {"risk_level": "medium"}},
                {"evidence_name": "收据", "opinion": {"risk_level": "low"}},
            ],
            "cross_exam_last_updated": "2026-02-02",
        }
        result = await MockTrialReportService().get_report("s2")
        assert result["mode"] == "cross_exam"
        assert result["status"] == "complete"
        assert result["summary"] == {"total": 3, "high_risk": 1, "medium_risk": 1, "low_risk": 1}
        assert len(result["results"]) == 3
        assert result["last_updated"] == "2026-02-02"

    @pytest.mark.asyncio
    async def test_cross_exam_empty_results(self, mock_repo: MagicMock) -> None:
        mock_repo.get_metadata.return_value = {"mock_trial_mode": "cross_exam"}
        result = await MockTrialReportService().get_report("s2")
        assert result["status"] == "no_data"
        assert result["summary"]["total"] == 0

    @pytest.mark.asyncio
    async def test_debate_mode(self, mock_repo: MagicMock) -> None:
        mock_repo.get_metadata.return_value = {
            "mock_trial_mode": "debate",
            "debate_history": [
                {"role": "user", "content": "观点1"},
                {"role": "assistant", "content": "反驳1"},
                {"role": "user", "content": "观点2"},
            ],
            "debate_selected_focus": {"topic": "利息"},
            "debate_last_updated": "2026-03-03",
        }
        result = await MockTrialReportService().get_report("s3")
        assert result["mode"] == "debate"
        assert result["rounds"] == 2  # 仅统计 user 轮次
        assert result["focus"] == {"topic": "利息"}
        assert len(result["history"]) == 3

    @pytest.mark.asyncio
    async def test_unknown_mode_returns_no_data(self, mock_repo: MagicMock) -> None:
        mock_repo.get_metadata.return_value = {"mock_trial_mode": "rocket_science"}
        result = await MockTrialReportService().get_report("s4")
        assert result == {"mode": "rocket_science", "status": "no_data"}

    @pytest.mark.asyncio
    async def test_no_mode_returns_no_data(self, mock_repo: MagicMock) -> None:
        mock_repo.get_metadata.return_value = {}
        result = await MockTrialReportService().get_report("s5")
        assert result == {"mode": "", "status": "no_data"}


class TestSaveJudgeReport:
    @pytest.mark.asyncio
    async def test_writes_all_keys(self, mock_repo: MagicMock) -> None:
        await MockTrialReportService().save_judge_report(
            "s1", report={"结论": "胜诉"}, model="gpt-x", token_usage={"total": 99}
        )
        patch_dict = mock_repo.update_metadata.await_args.args[1]
        assert patch_dict["judge_report"] == {"结论": "胜诉"}
        assert patch_dict["judge_report_model"] == "gpt-x"
        assert patch_dict["judge_report_token_usage"] == {"total": 99}
        assert patch_dict["judge_report_saved_at"]  # ISO 时间戳非空


class TestSaveCrossExamResult:
    @pytest.mark.asyncio
    async def test_appends_to_existing_results(self, mock_repo: MagicMock) -> None:
        mock_repo.get_metadata.return_value = {
            "cross_exam_results": [{"evidence_name": "旧证据", "opinion": {}}],
        }
        await MockTrialReportService().save_cross_exam_result(
            "s1", evidence_name="新证据", opinion={"risk_level": "high"}
        )
        patch_dict = mock_repo.update_metadata.await_args.args[1]
        results = patch_dict["cross_exam_results"]
        assert len(results) == 2
        assert results[0]["evidence_name"] == "旧证据"
        assert results[1] == {"evidence_name": "新证据", "opinion": {"risk_level": "high"}}
        assert patch_dict["cross_exam_last_updated"]

    @pytest.mark.asyncio
    async def test_first_result_creates_list(self, mock_repo: MagicMock) -> None:
        mock_repo.get_metadata.return_value = {}
        await MockTrialReportService().save_cross_exam_result("s1", evidence_name="首份", opinion={})
        patch_dict = mock_repo.update_metadata.await_args.args[1]
        assert len(patch_dict["cross_exam_results"]) == 1


class TestSaveDebateHistory:
    @pytest.mark.asyncio
    async def test_saves_history_with_focus(self, mock_repo: MagicMock) -> None:
        history: list[dict[str, str]] = [{"role": "user", "content": "观点"}]
        await MockTrialReportService().save_debate_history("s1", history, focus={"topic": "合同效力"})
        patch_dict = mock_repo.update_metadata.await_args.args[1]
        assert patch_dict["debate_history"] == history
        assert patch_dict["debate_selected_focus"] == {"topic": "合同效力"}
        assert patch_dict["debate_last_updated"]

    @pytest.mark.asyncio
    async def test_saves_history_without_focus(self, mock_repo: MagicMock) -> None:
        await MockTrialReportService().save_debate_history("s1", [], focus=None)
        patch_dict = mock_repo.update_metadata.await_args.args[1]
        assert "debate_selected_focus" not in patch_dict


class TestNowIso:
    def test_returns_utc_iso_string(self) -> None:
        value: Any = MockTrialReportService()._now_iso()
        assert isinstance(value, str)
        assert "+00:00" in value or value.endswith("Z")
