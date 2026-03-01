"""模拟庭审功能测试."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.chains.mock_trial_schemas import (
    CrossExamOpinion,
    DisputeFocus,
    EvidenceExamItem,
    JudgePerspectiveReport,
)
from apps.litigation_ai.models.choices import MockTrialMode, SessionType
from apps.litigation_ai.services.mock_trial.types import MockTrialContext, MockTrialStep


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def case_info() -> dict[str, Any]:
    return {
        "case_name": "张三诉李四民间借贷纠纷",
        "cause_of_action": "民间借贷纠纷",
        "target_amount": "100000",
        "parties": {"plaintiff": "张三", "defendant": "李四"},
        "case_stage": "一审",
    }


@pytest.fixture
def evidence_info() -> dict[str, Any]:
    return {
        "name": "借条",
        "description": "被告于2024年1月1日出具的借条",
        "evidence_type": "书证",
        "list_id": 1,
    }


@pytest.fixture
def evidence_list(evidence_info: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        evidence_info,
        {"name": "转账记录", "description": "银行转账凭证", "evidence_type": "书证", "list_id": 2},
    ]


@pytest.fixture
def mock_send_cb() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def ctx() -> MockTrialContext:
    return MockTrialContext(
        session_id="test-session-id",
        case_id=1,
        user_id=1,
        current_step=MockTrialStep.INIT,
    )


# ============================================================
# 1. Schema 验证
# ============================================================

class TestSchemas:
    def test_cross_exam_opinion_valid(self) -> None:
        data = {
            "evidence_name": "借条",
            "authenticity": {"opinion": "真实性存疑", "challenge_strength": "strong"},
            "legality": {"opinion": "合法", "challenge_strength": "weak"},
            "relevance": {"opinion": "关联性不足", "challenge_strength": "moderate"},
            "proof_power": {"opinion": "证明力有限", "challenge_strength": "moderate"},
            "suggested_response": "提供原件",
            "risk_level": "high",
        }
        obj = CrossExamOpinion.model_validate(data)
        assert obj.risk_level == "high"
        assert obj.authenticity.challenge_strength == "strong"

    def test_dispute_focus_valid(self) -> None:
        data = {
            "description": "借款事实是否成立",
            "focus_type": "事实争议",
            "plaintiff_position": "借款已交付",
            "defendant_position": "未收到借款",
            "key_evidence": ["借条", "转账记录"],
            "burden_of_proof": "原告",
        }
        obj = DisputeFocus.model_validate(data)
        assert obj.focus_type == "事实争议"
        assert len(obj.key_evidence) == 2

    def test_judge_perspective_report_valid(self) -> None:
        data = {
            "dispute_focuses": [
                {
                    "description": "借款事实",
                    "focus_type": "事实争议",
                    "plaintiff_position": "已交付",
                    "defendant_position": "未收到",
                    "key_evidence": [],
                    "burden_of_proof": "原告",
                }
            ],
            "evidence_strength_comparison": [
                {
                    "focus": "借款事实",
                    "plaintiff_strength": "strong",
                    "defendant_strength": "weak",
                    "analysis": "原告证据充分",
                }
            ],
            "risk_assessment": "风险较低",
            "judge_questions": ["借款交付方式？"],
            "overall_win_probability": "70%-80%",
            "recommended_strategy": "强调转账记录",
        }
        obj = JudgePerspectiveReport.model_validate(data)
        assert len(obj.dispute_focuses) == 1
        assert obj.overall_win_probability == "70%-80%"


# ============================================================
# 2. MockTrialStep 枚举 & MockTrialContext
# ============================================================

class TestTypes:
    def test_step_values(self) -> None:
        assert MockTrialStep.INIT.value == "mt_init"
        assert MockTrialStep.MODE_SELECT.value == "mt_mode_select"
        assert MockTrialStep.SIMULATION.value == "mt_simulation"
        assert MockTrialStep.SUMMARY.value == "mt_summary"

    def test_context_creation(self) -> None:
        ctx = MockTrialContext(session_id="abc", case_id=1, user_id=2, current_step=MockTrialStep.INIT)
        assert ctx.session_id == "abc"
        assert ctx.current_step == MockTrialStep.INIT


# ============================================================
# 3. MockTrialFlowService — 模式解析
# ============================================================

class TestFlowServiceModeParsing:
    def setup_method(self) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService
        self.flow = MockTrialFlowService()

    def test_parse_mode_number(self) -> None:
        assert self.flow._parse_mode("1") == MockTrialMode.JUDGE
        assert self.flow._parse_mode("2") == MockTrialMode.CROSS_EXAM
        assert self.flow._parse_mode("3") == MockTrialMode.DEBATE

    def test_parse_mode_chinese(self) -> None:
        assert self.flow._parse_mode("法官视角") == MockTrialMode.JUDGE
        assert self.flow._parse_mode("质证模拟") == MockTrialMode.CROSS_EXAM
        assert self.flow._parse_mode("辩论模拟") == MockTrialMode.DEBATE

    def test_parse_mode_invalid(self) -> None:
        assert self.flow._parse_mode("") is None
        assert self.flow._parse_mode("abc") is None
        assert self.flow._parse_mode("4") is None

    def test_parse_step(self) -> None:
        assert self.flow.parse_step(None) == MockTrialStep.INIT
        assert self.flow.parse_step("") == MockTrialStep.INIT
        assert self.flow.parse_step("mt_mode_select") == MockTrialStep.MODE_SELECT
        assert self.flow.parse_step("invalid") == MockTrialStep.INIT


# ============================================================
# 4. MockTrialFlowService — handle_init
# ============================================================

class TestFlowServiceInit:
    @pytest.mark.asyncio
    async def test_handle_init_sends_welcome(
        self, ctx: MockTrialContext, mock_send_cb: AsyncMock
    ) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        flow = MockTrialFlowService()
        flow._get_case_brief = AsyncMock(return_value={  # type: ignore[method-assign]
            "case_name": "测试案件", "cause_of_action": "民间借贷纠纷",
        })
        flow._messenger = MagicMock()
        flow._messenger.send = AsyncMock()
        flow._session_repo = MagicMock()
        flow._session_repo.set_step = AsyncMock()

        await flow.handle_init(ctx, mock_send_cb)

        # 验证发送了欢迎消息
        flow._messenger.send.assert_called_once()
        call_args = flow._messenger.send.call_args
        payload = call_args[0][1]
        assert "模拟庭审" in payload["content"]
        assert "1️⃣" in payload["content"]

        # 验证步骤设置为 MODE_SELECT
        flow._session_repo.set_step.assert_called_once_with(ctx.session_id, MockTrialStep.MODE_SELECT.value)


# ============================================================
# 5. MockTrialFlowService — handle_mode_select
# ============================================================

class TestFlowServiceModeSelect:
    @pytest.mark.asyncio
    async def test_invalid_mode_sends_error(
        self, ctx: MockTrialContext, mock_send_cb: AsyncMock
    ) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        flow = MockTrialFlowService()
        flow._messenger = MagicMock()
        flow._messenger.send = AsyncMock()

        await flow.handle_mode_select(ctx, "invalid", mock_send_cb)

        flow._messenger.send.assert_called_once()
        payload = flow._messenger.send.call_args[0][1]
        assert "未识别" in payload["content"]

    @pytest.mark.asyncio
    async def test_judge_mode_triggers_analysis(
        self, ctx: MockTrialContext, mock_send_cb: AsyncMock
    ) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        flow = MockTrialFlowService()
        flow._messenger = MagicMock()
        flow._messenger.send = AsyncMock()
        flow._messenger.persist_message = AsyncMock()
        flow._session_repo = MagicMock()
        flow._session_repo.update_metadata = AsyncMock()
        flow._session_repo.set_step = AsyncMock()
        flow._run_judge_analysis = AsyncMock()  # type: ignore[method-assign]

        await flow.handle_mode_select(ctx, "1", mock_send_cb)

        flow._session_repo.update_metadata.assert_called_once_with(ctx.session_id, {"mock_trial_mode": MockTrialMode.JUDGE})
        flow._run_judge_analysis.assert_called_once()


# ============================================================
# 6. CrossExamService
# ============================================================

class TestCrossExamService:
    @pytest.mark.asyncio
    async def test_examine_single(self, case_info: dict[str, Any], evidence_info: dict[str, Any]) -> None:
        from apps.litigation_ai.services.mock_trial.cross_exam_service import CrossExamService

        fake_opinion = {
            "evidence_name": "借条",
            "authenticity": {"opinion": "存疑", "challenge_strength": "strong"},
            "legality": {"opinion": "合法", "challenge_strength": "weak"},
            "relevance": {"opinion": "关联", "challenge_strength": "moderate"},
            "proof_power": {"opinion": "有限", "challenge_strength": "moderate"},
            "suggested_response": "提供原件",
            "risk_level": "high",
        }

        from apps.litigation_ai.chains.mock_trial_chains import CrossExamResult
        mock_result = CrossExamResult(opinion=fake_opinion, model="test", token_usage={})

        with patch("apps.litigation_ai.services.mock_trial.cross_exam_service.CrossExamChain") as MockChain:
            instance = MockChain.return_value
            instance.arun = AsyncMock(return_value=mock_result)

            svc = CrossExamService()
            result = await svc.examine_single(case_info=case_info, evidence_info=evidence_info)

            assert result.opinion["risk_level"] == "high"
            instance.arun.assert_called_once()


# ============================================================
# 7. DebateService
# ============================================================

class TestDebateService:
    @pytest.mark.asyncio
    async def test_analyze_focuses(self, case_info: dict[str, Any]) -> None:
        from apps.litigation_ai.services.mock_trial.debate_service import DebateService

        from apps.litigation_ai.chains.mock_trial_chains import DisputeFocusResult
        mock_result = DisputeFocusResult(
            focuses=[{"description": "借款事实", "focus_type": "事实争议", "plaintiff_position": "已交付",
                       "defendant_position": "未收到", "key_evidence": [], "burden_of_proof": "原告"}],
            model="test",
        )

        with patch("apps.litigation_ai.services.mock_trial.debate_service.DisputeFocusChain") as MockChain:
            instance = MockChain.return_value
            instance.arun = AsyncMock(return_value=mock_result)

            svc = DebateService()
            result = await svc.analyze_focuses(case_info=case_info, evidence_text="借条")

            assert len(result.focuses) == 1
            assert result.focuses[0]["description"] == "借款事实"

    @pytest.mark.asyncio
    async def test_debate_turn(self, case_info: dict[str, Any]) -> None:
        from apps.litigation_ai.services.mock_trial.debate_service import DebateService

        from apps.litigation_ai.chains.mock_trial_chains import DebateResult
        mock_result = DebateResult(rebuttal="反驳内容", model="test")

        with patch("apps.litigation_ai.services.mock_trial.debate_service.DebateChain") as MockChain:
            instance = MockChain.return_value
            instance.arun = AsyncMock(return_value=mock_result)

            svc = DebateService()
            result = await svc.debate_turn(
                case_info=case_info,
                focus={"description": "借款事实", "defendant_position": "未收到"},
                user_argument="借款已通过银行转账交付",
                history=[],
            )

            assert result.rebuttal == "反驳内容"


# ============================================================
# 8. MockTrialReportService
# ============================================================

class TestReportService:
    @pytest.mark.asyncio
    async def test_judge_report(self) -> None:
        from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService

        svc = MockTrialReportService()
        metadata = {"mock_trial_mode": "judge", "judge_report": {"risk_assessment": "低风险"}}

        with patch.object(svc, "get_report", wraps=svc.get_report):
            # 直接测试内部方法
            result = svc._judge_report(metadata)
            assert result["status"] == "complete"
            assert result["report"]["risk_assessment"] == "低风险"

    @pytest.mark.asyncio
    async def test_cross_exam_report(self) -> None:
        from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService

        svc = MockTrialReportService()
        metadata = {
            "mock_trial_mode": "cross_exam",
            "cross_exam_results": [
                {"evidence_name": "借条", "opinion": {"risk_level": "high"}},
                {"evidence_name": "转账记录", "opinion": {"risk_level": "low"}},
            ],
        }
        result = svc._cross_exam_report(metadata)
        assert result["summary"]["total"] == 2
        assert result["summary"]["high_risk"] == 1
        assert result["summary"]["low_risk"] == 1

    @pytest.mark.asyncio
    async def test_debate_report(self) -> None:
        from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService

        svc = MockTrialReportService()
        metadata = {
            "mock_trial_mode": "debate",
            "debate_selected_focus": {"description": "借款事实"},
            "debate_history": [
                {"role": "user", "content": "论点1"},
                {"role": "opponent", "content": "反驳1"},
            ],
        }
        result = svc._debate_report(metadata)
        assert result["rounds"] == 1
        assert result["focus"]["description"] == "借款事实"

    def test_no_data_report(self) -> None:
        from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService

        svc = MockTrialReportService()
        result = svc._judge_report({"mock_trial_mode": "judge"})
        assert result["status"] == "no_data"


# ============================================================
# 9. Flow — format helpers
# ============================================================

class TestFormatHelpers:
    def test_format_judge_report(self) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        flow = MockTrialFlowService()
        report = {
            "dispute_focuses": [
                {"description": "借款事实", "focus_type": "事实争议", "plaintiff_position": "已交付",
                 "defendant_position": "未收到", "burden_of_proof": "原告", "key_evidence": ["借条"]},
            ],
            "evidence_strength_comparison": [
                {"focus": "借款事实", "plaintiff_strength": "strong", "defendant_strength": "weak", "analysis": "原告证据充分"},
            ],
            "judge_questions": ["借款交付方式？"],
            "risk_assessment": "风险较低",
            "overall_win_probability": "70%-80%",
            "recommended_strategy": "强调转账记录",
        }
        result = flow._format_judge_report(report)
        assert "法官视角分析报告" in result
        assert "借款事实" in result
        assert "70%-80%" in result
        assert "借条" in result

    def test_format_cross_exam_opinion(self) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        flow = MockTrialFlowService()
        ev = {"name": "借条"}
        opinion = {
            "authenticity": {"opinion": "存疑", "challenge_strength": "strong"},
            "legality": {"opinion": "合法", "challenge_strength": "weak"},
            "relevance": {"opinion": "关联", "challenge_strength": "moderate"},
            "proof_power": {"opinion": "有限", "challenge_strength": "moderate"},
            "risk_level": "high",
            "suggested_response": "提供原件",
        }
        result = flow._format_cross_exam_opinion(ev, opinion)
        assert "借条" in result
        assert "真实性" in result
        assert "🔴" in result  # strong → 🔴


# ============================================================
# 10. Flow — cross exam flow (mocked)
# ============================================================

class TestCrossExamFlow:
    @pytest.mark.asyncio
    async def test_start_cross_exam_no_evidence(
        self, ctx: MockTrialContext, mock_send_cb: AsyncMock
    ) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        flow = MockTrialFlowService()
        flow._messenger = MagicMock()
        flow._messenger.send = AsyncMock()
        flow._session_repo = MagicMock()
        flow._session_repo.set_step = AsyncMock()

        with patch("apps.litigation_ai.services.mock_trial.cross_exam_service.CrossExamService.load_evidence_list", new_callable=AsyncMock, return_value=[]):
            await flow._start_cross_exam(ctx, mock_send_cb)

        # 无证据时应提示并跳到 SUMMARY
        payload = flow._messenger.send.call_args[0][1]
        assert "暂无证据" in payload["content"]
        flow._session_repo.set_step.assert_called_with(ctx.session_id, MockTrialStep.SUMMARY.value)

    @pytest.mark.asyncio
    async def test_handle_cross_exam_skip(
        self, ctx: MockTrialContext, mock_send_cb: AsyncMock
    ) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        flow = MockTrialFlowService()
        flow._messenger = MagicMock()
        flow._messenger.send = AsyncMock()
        flow._session_repo = MagicMock()
        flow._session_repo.get_metadata = AsyncMock(return_value={
            "cross_exam_evidence": [{"name": "a"}, {"name": "b"}],
            "cross_exam_index": 0,
            "cross_exam_results": [],
        })
        flow._session_repo.set_step = AsyncMock()

        await flow._handle_cross_exam_response(ctx, "跳过", mock_send_cb)

        # 跳过应直接到 SUMMARY
        flow._session_repo.set_step.assert_called_with(ctx.session_id, MockTrialStep.SUMMARY.value)


# ============================================================
# 11. Flow — debate flow (mocked)
# ============================================================

class TestDebateFlow:
    @pytest.mark.asyncio
    async def test_handle_debate_end(
        self, ctx: MockTrialContext, mock_send_cb: AsyncMock
    ) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        flow = MockTrialFlowService()
        flow._messenger = MagicMock()
        flow._messenger.send = AsyncMock()
        flow._session_repo = MagicMock()
        flow._session_repo.get_metadata = AsyncMock(return_value={
            "debate_focuses": [{"description": "焦点1"}],
            "debate_selected_focus": {"description": "焦点1"},
            "debate_history": [{"role": "user", "content": "论点"}, {"role": "opponent", "content": "反驳"}],
        })
        flow._session_repo.set_step = AsyncMock()

        await flow._handle_debate_turn(ctx, "结束", mock_send_cb)

        flow._session_repo.set_step.assert_called_with(ctx.session_id, MockTrialStep.SUMMARY.value)
        payload = flow._messenger.send.call_args[0][1]
        assert "辩论模拟结束" in payload["content"]

    @pytest.mark.asyncio
    async def test_handle_debate_select_focus(
        self, ctx: MockTrialContext, mock_send_cb: AsyncMock
    ) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        flow = MockTrialFlowService()
        flow._messenger = MagicMock()
        flow._messenger.send = AsyncMock()
        flow._session_repo = MagicMock()
        flow._session_repo.get_metadata = AsyncMock(return_value={
            "debate_focuses": [{"description": "焦点1"}, {"description": "焦点2"}],
            "debate_selected_focus": None,
            "debate_history": [],
        })
        flow._session_repo.update_metadata = AsyncMock()

        await flow._handle_debate_turn(ctx, "1", mock_send_cb)

        # 应更新 metadata 选择焦点
        flow._session_repo.update_metadata.assert_called_once_with(
            ctx.session_id, {"debate_selected_focus": {"description": "焦点1"}}
        )


# ============================================================
# 12. Model — SessionType choices
# ============================================================

class TestModelChoices:
    def test_session_type_choices(self) -> None:
        assert SessionType.DOC_GEN == "doc_gen"
        assert SessionType.MOCK_TRIAL == "mock_trial"

    def test_mock_trial_mode_choices(self) -> None:
        assert MockTrialMode.JUDGE == "judge"
        assert MockTrialMode.CROSS_EXAM == "cross_exam"
        assert MockTrialMode.DEBATE == "debate"


# ============================================================
# 13. DB integration — Session CRUD
# ============================================================

@pytest.mark.django_db
class TestSessionDB:
    def test_create_mock_trial_session(self, case: Any, lawyer: Any) -> None:
        from apps.litigation_ai.models import LitigationSession

        session = LitigationSession.objects.create(
            case=case,
            user=lawyer,
            session_type="mock_trial",
            status="active",
            metadata={"mock_trial_mode": "judge"},
        )
        assert session.session_type == "mock_trial"
        assert session.metadata["mock_trial_mode"] == "judge"

    def test_filter_by_session_type(self, case: Any, lawyer: Any) -> None:
        from apps.litigation_ai.models import LitigationSession

        LitigationSession.objects.create(case=case, user=lawyer, session_type="doc_gen")
        LitigationSession.objects.create(case=case, user=lawyer, session_type="mock_trial")

        doc_sessions = LitigationSession.objects.filter(session_type="doc_gen")
        mock_sessions = LitigationSession.objects.filter(session_type="mock_trial")

        assert doc_sessions.count() == 1
        assert mock_sessions.count() == 1


# ============================================================
# 14. API — mock trial endpoints
# ============================================================

@pytest.mark.django_db
class TestMockTrialAPI:
    def test_create_session(self, authenticated_client: Any, case: Any) -> None:
        resp = authenticated_client.post(
            "/api/v1/mock-trial/sessions",
            data=json.dumps({"case_id": case.id}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_type"] == "mock_trial"
        assert data["case_id"] == case.id

    def test_list_sessions_via_model(self, authenticated_client: Any, case: Any, lawyer: Any) -> None:
        """直接验证 model 层过滤，绕过 core_conversation_history 依赖."""
        from apps.litigation_ai.models import LitigationSession

        LitigationSession.objects.create(case=case, user=lawyer, session_type="mock_trial")
        LitigationSession.objects.create(case=case, user=lawyer, session_type="doc_gen")

        mock_sessions = LitigationSession.objects.filter(session_type="mock_trial", case_id=case.id)
        assert mock_sessions.count() == 1

    def test_get_session_via_model(self, authenticated_client: Any, case: Any, lawyer: Any) -> None:
        """直接验证 model 层获取."""
        from apps.litigation_ai.models import LitigationSession

        session = LitigationSession.objects.create(case=case, user=lawyer, session_type="mock_trial", metadata={"test": True})
        fetched = LitigationSession.objects.filter(session_id=session.session_id, session_type="mock_trial").first()
        assert fetched is not None
        assert fetched.metadata["test"] is True

    def test_delete_session_via_model(self, authenticated_client: Any, case: Any, lawyer: Any) -> None:
        """直接验证 model 层删除."""
        from apps.litigation_ai.models import LitigationSession

        session = LitigationSession.objects.create(case=case, user=lawyer, session_type="mock_trial")
        sid = session.session_id
        # 使用 _raw_delete 避免 cascade 触发 core_conversation_history
        LitigationSession.objects.filter(session_id=sid)._raw_delete(LitigationSession.objects.db)
        assert not LitigationSession.objects.filter(session_id=sid).exists()
