"""Tests for MockTrialFlowService."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.models.choices import MockTrialMode
from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService
from apps.litigation_ai.services.mock_trial.types import (
    AdversarialConfig,
    MockTrialContext,
    MockTrialStep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LAZY_JPS = "apps.litigation_ai.services.mock_trial.judge_perspective_service.JudgePerspectiveService"
_LAZY_CES = "apps.litigation_ai.services.mock_trial.cross_exam_service.CrossExamService"
_LAZY_DS = "apps.litigation_ai.services.mock_trial.debate_service.DebateService"
_LAZY_ADV = "apps.litigation_ai.services.mock_trial.adversarial_service.AdversarialTrialService"
_LAZY_ADV_LABELS = "apps.litigation_ai.services.mock_trial.adversarial_service.ROLE_LABELS"
_LAZY_LLM_CFG = "apps.core.llm.config.LLMConfig"


def _ctx(
    session_id: str = "sess-1",
    case_id: int = 1,
    user_id: int = 10,
    step: MockTrialStep = MockTrialStep.INIT,
) -> MockTrialContext:
    return MockTrialContext(
        session_id=session_id,
        case_id=case_id,
        user_id=user_id,
        current_step=step,
    )


def _make_service() -> MockTrialFlowService:
    svc = MockTrialFlowService()
    svc._session_repo = MagicMock()
    svc._session_repo.set_step = AsyncMock()
    svc._session_repo.get_metadata = AsyncMock(return_value={})
    svc._session_repo.update_metadata = AsyncMock()
    svc._messenger = MagicMock()
    svc._messenger.send = AsyncMock()
    svc._messenger.persist_message = AsyncMock()
    svc._conversation_service = MagicMock()
    return svc


# ===========================================================================
# Pure / sync tests
# ===========================================================================


class TestParseStep:
    def test_none_returns_init(self) -> None:
        svc = _make_service()
        assert svc.parse_step(None) == MockTrialStep.INIT

    def test_empty_string_returns_init(self) -> None:
        svc = _make_service()
        assert svc.parse_step("") == MockTrialStep.INIT

    def test_valid_step(self) -> None:
        svc = _make_service()
        assert svc.parse_step("mt_init") == MockTrialStep.INIT

    def test_invalid_step_returns_init(self) -> None:
        svc = _make_service()
        assert svc.parse_step("nonexistent_step") == MockTrialStep.INIT


class TestGetCurrentStep:
    def test_delegates_to_repo(self) -> None:
        svc = _make_service()
        svc._session_repo.get_step_value_sync.return_value = "mt_simulation"
        assert svc.get_current_step("sess-1") == MockTrialStep.SIMULATION


class TestParseMode:
    def test_judge_keywords(self) -> None:
        svc = _make_service()
        assert svc._parse_mode("1") == MockTrialMode.JUDGE
        assert svc._parse_mode("法官") == MockTrialMode.JUDGE
        assert svc._parse_mode("法官视角") == MockTrialMode.JUDGE

    def test_cross_exam_keywords(self) -> None:
        svc = _make_service()
        assert svc._parse_mode("2") == MockTrialMode.CROSS_EXAM
        assert svc._parse_mode("质证") == MockTrialMode.CROSS_EXAM
        assert svc._parse_mode("质证模拟") == MockTrialMode.CROSS_EXAM

    def test_debate_keywords(self) -> None:
        svc = _make_service()
        assert svc._parse_mode("3") == MockTrialMode.DEBATE
        assert svc._parse_mode("辩论") == MockTrialMode.DEBATE
        assert svc._parse_mode("辩论模拟") == MockTrialMode.DEBATE

    def test_adversarial_keywords(self) -> None:
        svc = _make_service()
        assert svc._parse_mode("4") == MockTrialMode.ADVERSARIAL
        assert svc._parse_mode("对抗") == MockTrialMode.ADVERSARIAL
        assert svc._parse_mode("多agent对抗") == MockTrialMode.ADVERSARIAL

    def test_unrecognized_returns_none(self) -> None:
        svc = _make_service()
        assert svc._parse_mode("xyz") is None
        assert svc._parse_mode("") is None
        assert svc._parse_mode(None) is None


class TestFormatJudgeReport:
    def test_full_report(self) -> None:
        svc = _make_service()
        report = {
            "dispute_focuses": [
                {
                    "description": "合同效力",
                    "focus_type": "法律适用",
                    "plaintiff_position": "合同有效",
                    "defendant_position": "合同无效",
                    "burden_of_proof": "被告",
                    "key_evidence": ["合同文本", "聊天记录"],
                },
            ],
            "evidence_strength_comparison": [
                {
                    "focus": "合同效力",
                    "plaintiff_strength": "强",
                    "defendant_strength": "弱",
                    "analysis": "原告证据链完整",
                },
            ],
            "judge_questions": ["合同签订时双方是否自愿？"],
            "risk_assessment": "中等风险",
            "overall_win_probability": "70%",
            "recommended_strategy": "重点举证合同签订过程",
        }
        text = svc._format_judge_report(report)
        assert "法官视角分析报告" in text
        assert "合同效力" in text
        assert "合同文本、聊天记录" in text
        assert "原告证据：强" in text
        assert "合同签订时双方是否自愿？" in text
        assert "中等风险" in text
        assert "70%" in text

    def test_empty_report(self) -> None:
        svc = _make_service()
        text = svc._format_judge_report({})
        assert "法官视角分析报告" in text
        assert "风险评估" in text
        assert "胜诉概率" in text


class TestFormatCrossExamOpinion:
    def test_full_opinion(self) -> None:
        svc = _make_service()
        ev = {"name": "合同文本"}
        opinion = {
            "authenticity": {"challenge_strength": "strong", "opinion": "真实性存疑"},
            "legality": {"challenge_strength": "weak", "opinion": "合法"},
            "relevance": {"challenge_strength": "moderate", "opinion": "部分关联"},
            "proof_power": {"challenge_strength": "weak", "opinion": "证明力不足"},
            "risk_level": "high",
            "suggested_response": "准备原件",
        }
        text = svc._format_cross_exam_opinion(ev, opinion)
        assert "质证意见 — 合同文本" in text
        assert "真实性" in text
        assert "high" in text

    def test_missing_fields(self) -> None:
        svc = _make_service()
        text = svc._format_cross_exam_opinion({}, {})
        assert "未命名" in text


# ===========================================================================
# Async tests — init
# ===========================================================================


class TestHandleInit:
    @pytest.mark.asyncio
    async def test_sends_intro_and_sets_mode_select(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        with patch.object(svc, "_get_case_brief", new_callable=AsyncMock, return_value={"case_name": "张三诉李四", "cause_of_action": "合同纠纷"}):
            await svc.handle_init(ctx, send_cb)

        svc._messenger.send.assert_awaited_once()
        svc._session_repo.set_step.assert_awaited_once_with("sess-1", MockTrialStep.MODE_SELECT.value)


# ===========================================================================
# Async tests — mode select
# ===========================================================================


class TestHandleModeSelect:
    @pytest.mark.asyncio
    async def test_judge_mode(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        with patch.object(svc, "_run_judge_analysis", new_callable=AsyncMock) as mock_run:
            await svc.handle_mode_select(ctx, "1", send_cb)
            mock_run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cross_exam_mode(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        with patch.object(svc, "_start_cross_exam", new_callable=AsyncMock) as mock_start:
            await svc.handle_mode_select(ctx, "2", send_cb)
            mock_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_debate_mode(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        with patch.object(svc, "_start_debate_focus", new_callable=AsyncMock) as mock_start:
            await svc.handle_mode_select(ctx, "3", send_cb)
            mock_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_adversarial_mode(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        with patch.object(svc, "_send_model_config_prompt", new_callable=AsyncMock) as mock_cfg:
            await svc.handle_mode_select(ctx, "4", send_cb)
            mock_cfg.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_mode_sends_error(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        await svc.handle_mode_select(ctx, "xyz", send_cb)
        svc._messenger.send.assert_awaited_once()
        call_args = svc._messenger.send.call_args[0]
        assert "未识别模式" in call_args[1]["content"]


# ===========================================================================
# Async tests — simulation dispatch
# ===========================================================================


class TestHandleSimulation:
    @pytest.mark.asyncio
    async def test_dispatches_adversarial(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(return_value={"mock_trial_mode": MockTrialMode.ADVERSARIAL})
        with patch.object(svc, "_handle_adversarial_input", new_callable=AsyncMock) as mock_h:
            await svc.handle_simulation(ctx, "test", send_cb)
            mock_h.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatches_cross_exam(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(return_value={"mock_trial_mode": MockTrialMode.CROSS_EXAM})
        with patch.object(svc, "_handle_cross_exam_response", new_callable=AsyncMock) as mock_h:
            await svc.handle_simulation(ctx, "test", send_cb)
            mock_h.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatches_debate(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(return_value={"mock_trial_mode": MockTrialMode.DEBATE})
        with patch.object(svc, "_handle_debate_turn", new_callable=AsyncMock) as mock_h:
            await svc.handle_simulation(ctx, "test", send_cb)
            mock_h.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_mode_sends_done_message(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(return_value={})
        await svc.handle_simulation(ctx, "test", send_cb)
        svc._messenger.send.assert_awaited_once()
        content = svc._messenger.send.call_args[0][1]["content"]
        assert "分析已完成" in content


# ===========================================================================
# Async tests — judge analysis
# ===========================================================================


class TestRunJudgeAnalysis:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        mock_result = {
            "report": {"risk_assessment": "低风险", "overall_win_probability": "80%"},
            "model": "gpt-4",
            "token_usage": 1000,
        }
        with patch(_LAZY_JPS) as MockJPS:
            instance = MockJPS.return_value
            instance.generate_analysis = AsyncMock(return_value=mock_result)
            await svc._run_judge_analysis(ctx, send_cb)

        svc._session_repo.set_step.assert_awaited_with("sess-1", MockTrialStep.SUMMARY.value)

    @pytest.mark.asyncio
    async def test_failure_sends_error(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        with patch(_LAZY_JPS) as MockJPS:
            instance = MockJPS.return_value
            instance.generate_analysis = AsyncMock(side_effect=RuntimeError("LLM failure"))
            await svc._run_judge_analysis(ctx, send_cb)

        error_call = svc._messenger.send.call_args[0]
        # Error payloads use "message" key, not "content"
        payload = error_call[1]
        assert "分析失败" in payload.get("message", payload.get("content", ""))


# ===========================================================================
# Async tests — cross exam
# ===========================================================================


class TestCrossExamFlow:
    @pytest.mark.asyncio
    async def test_no_evidence(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        with patch(_LAZY_CES) as MockCES:
            MockCES.return_value.load_evidence_list = AsyncMock(return_value=[])
            await svc._start_cross_exam(ctx, send_cb)

        svc._session_repo.set_step.assert_awaited_with("sess-1", MockTrialStep.SUMMARY.value)

    @pytest.mark.asyncio
    async def test_finish_cross_exam_counts_risks(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(
            return_value={
                "cross_exam_results": [
                    {"evidence_name": "A", "opinion": {"risk_level": "high"}},
                    {"evidence_name": "B", "opinion": {"risk_level": "medium"}},
                    {"evidence_name": "C", "opinion": {"risk_level": "low"}},
                ]
            }
        )
        await svc._finish_cross_exam(ctx, send_cb)
        content = svc._messenger.send.call_args[0][1]["content"]
        assert "高风险：1 份" in content
        assert "中风险：1 份" in content
        assert "低风险：1 份" in content

    @pytest.mark.asyncio
    async def test_handle_cross_exam_skip(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(return_value={"cross_exam_evidence": [], "cross_exam_index": 0})
        with patch.object(svc, "_finish_cross_exam", new_callable=AsyncMock) as mock_fin:
            await svc._handle_cross_exam_response(ctx, "跳过", send_cb)
            mock_fin.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_cross_exam_next(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        evidence_list = [{"name": "A"}, {"name": "B"}]
        svc._session_repo.get_metadata = AsyncMock(
            return_value={"cross_exam_evidence": evidence_list, "cross_exam_index": 0, "cross_exam_results": []}
        )
        svc._get_case_brief = AsyncMock(return_value={})

        with patch(_LAZY_CES) as MockCES:
            MockCES.return_value.examine_single = AsyncMock(return_value=MagicMock(opinion={"risk_level": "low"}))
            with patch.object(svc, "_send_evidence_menu", new_callable=AsyncMock) as mock_menu:
                await svc._handle_cross_exam_response(ctx, "下一份", send_cb)
                mock_menu.assert_awaited_once_with(ctx, send_cb, evidence_list, 1)


# ===========================================================================
# Async tests — debate
# ===========================================================================


class TestDebateFlow:
    @pytest.mark.asyncio
    async def test_select_focus(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        focuses = [{"description": "焦点1", "focus_type": "法律适用", "burden_of_proof": "原告"}]
        svc._session_repo.get_metadata = AsyncMock(
            return_value={"debate_focuses": focuses, "debate_selected_focus": None, "debate_history": []}
        )
        await svc._handle_debate_turn(ctx, "1", send_cb)
        svc._session_repo.update_metadata.assert_awaited()
        content = svc._messenger.send.call_args[0][1]["content"]
        assert "焦点1" in content

    @pytest.mark.asyncio
    async def test_select_focus_invalid_number(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(
            return_value={"debate_focuses": [{"description": "A"}], "debate_selected_focus": None, "debate_history": []}
        )
        await svc._handle_debate_turn(ctx, "5", send_cb)
        content = svc._messenger.send.call_args[0][1]["content"]
        assert "1-1" in content

    @pytest.mark.asyncio
    async def test_select_focus_non_numeric(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(
            return_value={"debate_focuses": [{"description": "A"}], "debate_selected_focus": None, "debate_history": []}
        )
        await svc._handle_debate_turn(ctx, "abc", send_cb)
        content = svc._messenger.send.call_args[0][1]["content"]
        assert "数字" in content

    @pytest.mark.asyncio
    async def test_end_debate(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(
            return_value={"debate_focuses": [], "debate_selected_focus": None, "debate_history": []}
        )
        with patch.object(svc, "_finish_debate", new_callable=AsyncMock) as mock_fin:
            await svc._handle_debate_turn(ctx, "结束", send_cb)
            mock_fin.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_debate_turn_success(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        selected = {"description": "焦点1"}
        history: list[dict[str, str]] = []
        svc._session_repo.get_metadata = AsyncMock(
            return_value={
                "debate_focuses": [selected],
                "debate_selected_focus": selected,
                "debate_history": history,
                "debate_difficulty": "medium",
            }
        )
        svc._get_case_brief = AsyncMock(return_value={})

        with patch(_LAZY_DS) as MockDS:
            turn_result = MagicMock()
            turn_result.rebuttal = "反驳内容"
            MockDS.return_value.debate_turn = AsyncMock(return_value=turn_result)
            await svc._handle_debate_turn(ctx, "我的论点", send_cb)

        send_cb.assert_called()
        svc._session_repo.update_metadata.assert_awaited()

    @pytest.mark.asyncio
    async def test_debate_turn_failure(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._session_repo.get_metadata = AsyncMock(
            return_value={
                "debate_focuses": [{"description": "X"}],
                "debate_selected_focus": {"description": "X"},
                "debate_history": [],
            }
        )
        svc._get_case_brief = AsyncMock(return_value={})

        with patch(_LAZY_DS) as MockDS:
            MockDS.return_value.debate_turn = AsyncMock(side_effect=RuntimeError("LLM error"))
            await svc._handle_debate_turn(ctx, "论点", send_cb)

        error_call = svc._messenger.send.call_args[0]
        payload = error_call[1]
        assert "辩论回合失败" in payload.get("message", payload.get("content", ""))

    @pytest.mark.asyncio
    async def test_finish_debate(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        history = [
            {"role": "user", "content": "a"},
            {"role": "opponent", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        await svc._finish_debate(ctx, send_cb, history)
        content = svc._messenger.send.call_args[0][1]["content"]
        assert "2 轮" in content
        svc._session_repo.set_step.assert_awaited_with("sess-1", MockTrialStep.SUMMARY.value)

    @pytest.mark.asyncio
    async def test_start_debate_focus_no_focuses(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        with (
            patch.object(svc, "_get_case_brief", new_callable=AsyncMock, return_value={}),
            patch.object(svc, "_get_evidence_text", new_callable=AsyncMock, return_value=""),
            patch(_LAZY_DS) as MockDS,
        ):
            MockDS.return_value.analyze_focuses = AsyncMock(return_value=MagicMock(focuses=[]))
            await svc._start_debate_focus(ctx, send_cb)

        svc._session_repo.set_step.assert_awaited_with("sess-1", MockTrialStep.SUMMARY.value)

    @pytest.mark.asyncio
    async def test_start_debate_focus_exception(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        with (
            patch.object(svc, "_get_case_brief", new_callable=AsyncMock, return_value={}),
            patch.object(svc, "_get_evidence_text", new_callable=AsyncMock, return_value=""),
            patch(_LAZY_DS) as MockDS,
        ):
            MockDS.return_value.analyze_focuses = AsyncMock(side_effect=RuntimeError("boom"))
            await svc._start_debate_focus(ctx, send_cb)

        error_call = svc._messenger.send.call_args[0]
        payload = error_call[1]
        assert "争议焦点归纳失败" in payload.get("message", payload.get("content", ""))


# ===========================================================================
# Adversarial config parsing
# ===========================================================================


class TestAdversarialConfigParsing:
    def test_default_config(self) -> None:
        svc = _make_service()
        config = svc._parse_adversarial_config("默认", ["m1", "m2"])
        assert config.user_role == "observer"
        assert config.debate_rounds == 10

    def test_custom_config(self) -> None:
        svc = _make_service()
        models = ["gpt-4o", "claude-3", "gemini-pro"]
        text = "原告模型: 1\n被告模型: 2\n法官模型: 3\n辩论轮数: 5\n角色: 原告\n审级: 二审"
        config = svc._parse_adversarial_config(text, models)
        assert config.plaintiff_model == "gpt-4o"
        assert config.defendant_model == "claude-3"
        assert config.judge_model == "gemini-pro"
        assert config.debate_rounds == 5
        assert config.user_role == "plaintiff"
        assert config.trial_level == "second"

    def test_min_rounds_is_3(self) -> None:
        svc = _make_service()
        config = svc._parse_adversarial_config("辩论轮数: 1", ["m1"])
        assert config.debate_rounds == 3

    def test_model_name_fuzzy_match(self) -> None:
        svc = _make_service()
        config = svc._parse_adversarial_config("原告模型: claude", ["gpt-4o", "claude-3-opus"])
        assert config.plaintiff_model == "claude-3-opus"

    def test_role_keyword_other(self) -> None:
        svc = _make_service()
        config = svc._parse_adversarial_config("角色: 观看", ["m1"])
        assert config.user_role == "observer"


# ===========================================================================
# Async tests — adversarial input
# ===========================================================================


class TestHandleAdversarialInput:
    @pytest.mark.asyncio
    async def test_export_report_no_transcript(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._adversarial_services = {}
        await svc._handle_adversarial_input(ctx, "导出报告", send_cb)
        send_cb.assert_awaited_once()
        assert "暂无庭审记录" in send_cb.call_args[0][0]["content"]

    @pytest.mark.asyncio
    async def test_end_debate(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        mock_service = MagicMock()
        mock_service.run_summary = AsyncMock()
        svc._adversarial_services = {"sess-1": mock_service}
        await svc._handle_adversarial_input(ctx, "结束辩论", send_cb)
        svc._session_repo.set_step.assert_awaited()

    @pytest.mark.asyncio
    async def test_role_switch(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        mock_service = MagicMock()
        mock_service.config = AdversarialConfig()
        svc._adversarial_services = {"sess-1": mock_service}
        svc._session_repo.get_metadata = AsyncMock(return_value={"adversarial_config": {}})

        await svc._handle_adversarial_input(ctx, "我代替原告", send_cb)
        send_cb.assert_awaited_once()
        assert "原告律师" in send_cb.call_args[0][0]["content"]

    @pytest.mark.asyncio
    async def test_pass_through_to_service(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        mock_service = MagicMock()
        mock_service.handle_user_input = AsyncMock()
        svc._adversarial_services = {"sess-1": mock_service}
        await svc._handle_adversarial_input(ctx, "我的发言", send_cb)
        mock_service.handle_user_input.assert_awaited_once()


# ===========================================================================
# Misc
# ===========================================================================


class TestSetStep:
    @pytest.mark.asyncio
    async def test_calls_repo(self) -> None:
        svc = _make_service()
        await svc._set_step("sess-1", MockTrialStep.SIMULATION)
        svc._session_repo.set_step.assert_awaited_once_with("sess-1", MockTrialStep.SIMULATION.value)


class TestLazyProperties:
    def test_session_repo_creates_instance(self) -> None:
        svc = MockTrialFlowService()
        svc._session_repo = None
        with patch("apps.litigation_ai.services.mock_trial.mock_trial_flow_service.LitigationSessionRepository") as MockRepo:
            _ = svc.session_repo
            MockRepo.assert_called_once()

    def test_messenger_creates_instance(self) -> None:
        svc = MockTrialFlowService()
        svc._messenger = None
        svc._conversation_service = MagicMock()
        with patch("apps.litigation_ai.services.mock_trial.mock_trial_flow_service.FlowMessenger") as MockMsg:
            _ = svc.messenger
            MockMsg.assert_called_once()

    def test_conversation_service_lazy(self) -> None:
        svc = MockTrialFlowService()
        svc._conversation_service = None
        with patch("apps.litigation_ai.services.mock_trial.mock_trial_flow_service.ConversationService", create=True):
            # The import is inside the method, but the service class isn't at module level
            # so we patch the actual import path
            pass
        # Just test that calling the method works when _conversation_service is set
        svc._conversation_service = MagicMock()
        assert svc._get_conversation_service() is svc._conversation_service


class TestHandleModelConfig:
    @pytest.mark.asyncio
    async def test_default_config_starts_trial(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        svc._get_case_brief = AsyncMock(return_value={})
        svc._get_evidence_text = AsyncMock(return_value="")

        with (
            patch(_LAZY_LLM_CFG) as MockLLM,
            patch(_LAZY_ADV) as MockAdv,
        ):
            MockLLM.DEFAULT_AVAILABLE_MODELS = ["m1", "m2"]
            adv_instance = MockAdv.return_value
            adv_instance.run_full_trial = AsyncMock()
            await svc.handle_model_config(ctx, "默认", send_cb)
            adv_instance.run_full_trial.assert_awaited_once()


class TestSendEvidenceMenu:
    @pytest.mark.asyncio
    async def test_sends_menu_and_progress(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()
        evidence_list = [
            {"name": "证据A", "evidence_type": "书证", "description": "合同"},
            {"name": "证据B", "evidence_type": "物证", "description": "照片"},
        ]
        svc._get_case_brief = AsyncMock(return_value={})

        with patch(_LAZY_CES) as MockCES:
            MockCES.return_value.examine_single = AsyncMock(
                return_value=MagicMock(opinion={"risk_level": "low"})
            )
            svc._session_repo.get_metadata = AsyncMock(return_value={"cross_exam_results": []})
            await svc._send_evidence_menu(ctx, send_cb, evidence_list, 0)

        # send_cb is called for progress update + assistant_complete (menu goes through messenger.send)
        assert send_cb.call_count >= 2


class TestExportAdversarialReport:
    @pytest.mark.asyncio
    async def test_with_transcript(self) -> None:
        svc = _make_service()
        ctx = _ctx()
        send_cb = AsyncMock()

        mock_service = MagicMock()
        mock_service.transcript = [
            {"stage": "opening", "role": "judge", "content": "开庭", "is_user": False},
            {"stage": "plaintiff_statement", "role": "plaintiff", "content": "陈述", "is_user": True},
        ]
        mock_service.case_info = {"case_name": "测试案件", "cause_of_action": "合同"}
        svc._adversarial_services = {"sess-1": mock_service}
        svc._session_repo.get_metadata = AsyncMock(
            return_value={
                "adversarial_config": {
                    "plaintiff_model": "gpt-4",
                    "defendant_model": "claude-3",
                    "judge_model": "gemini",
                    "debate_rounds": 10,
                }
            }
        )

        with patch(_LAZY_ADV_LABELS, {"judge": "审判长", "plaintiff": "原告"}):
            await svc._export_adversarial_report(ctx, send_cb)

        send_cb.assert_awaited()
        svc._session_repo.update_metadata.assert_awaited()
