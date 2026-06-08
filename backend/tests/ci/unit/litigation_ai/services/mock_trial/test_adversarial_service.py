"""Tests for litigation_ai.services.mock_trial.adversarial_service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService
from apps.litigation_ai.services.mock_trial.types import AdversarialConfig, MockTrialContext, MockTrialStep, TrialLevel


def _make_config(**overrides: Any) -> AdversarialConfig:
    return AdversarialConfig(
        plaintiff_model=overrides.get("plaintiff_model", ""),
        defendant_model=overrides.get("defendant_model", ""),
        judge_model=overrides.get("judge_model", ""),
        debate_rounds=overrides.get("debate_rounds", 2),
        user_role=overrides.get("user_role", "observer"),
        trial_level=overrides.get("trial_level", "first"),
    )


def _make_case_info() -> dict[str, Any]:
    return {
        "case_name": "Test Case",
        "cause_of_action": "Contract Dispute",
        "target_amount": "100000",
        "parties": [
            {"name": "Plaintiff Corp", "legal_status": "原告", "is_our_side": True},
            {"name": "Defendant LLC", "legal_status": "被告", "is_our_side": False},
        ],
    }


class TestAdversarialTrialServiceInit:
    def test_init_first_trial(self):
        config = _make_config(trial_level="first")
        svc = AdversarialTrialService(config, _make_case_info(), "evidence text")
        assert svc.is_second is False
        assert svc.transcript == []

    def test_init_second_trial(self):
        config = _make_config(trial_level="second")
        svc = AdversarialTrialService(config, _make_case_info(), "evidence text")
        assert svc.is_second is True


class TestAdversarialTrialServiceCaseBrief:
    def test_case_brief_contains_info(self):
        svc = AdversarialTrialService(_make_config(), _make_case_info(), "evidence")
        brief = svc._case_brief()
        assert "Test Case" in brief
        assert "Contract Dispute" in brief
        assert "100000" in brief
        assert "evidence" in brief


class TestAdversarialTrialServicePartyNames:
    def test_party_names(self):
        svc = AdversarialTrialService(_make_config(), _make_case_info(), "ev")
        p_name, d_name = svc._party_names()
        assert p_name == "Plaintiff Corp"
        assert d_name == "Defendant LLC"

    def test_party_names_fallback(self):
        info = {"case_name": "Test", "cause_of_action": "", "target_amount": "", "parties": []}
        svc = AdversarialTrialService(_make_config(), info, "")
        p_name, d_name = svc._party_names()
        assert p_name == "原告"
        assert d_name == "被告"


class TestAdversarialTrialServiceWaitOrAi:
    @pytest.mark.asyncio
    async def test_user_role_returns_none(self):
        config = _make_config(user_role="plaintiff")
        svc = AdversarialTrialService(config, _make_case_info(), "ev")
        send_cb = AsyncMock()
        result = await svc._wait_or_ai(svc.plaintiff, "prompt", send_cb, "test")
        assert result is None

    @pytest.mark.asyncio
    async def test_observer_role_uses_ai(self):
        config = _make_config(user_role="observer")
        svc = AdversarialTrialService(config, _make_case_info(), "ev")
        svc.plaintiff.respond = AsyncMock(return_value="AI response")
        send_cb = AsyncMock()
        result = await svc._wait_or_ai(svc.plaintiff, "prompt", send_cb, "test")
        assert result == "AI response"


class TestAdversarialTrialServicePhases:
    @pytest.mark.asyncio
    async def test_phase_1_opening_first(self):
        svc = AdversarialTrialService(_make_config(), _make_case_info(), "ev")
        send_cb = AsyncMock()
        await svc.phase_1_opening(send_cb)
        assert len(svc.transcript) >= 2  # clerk + judge

    @pytest.mark.asyncio
    async def test_phase_1_opening_second(self):
        svc = AdversarialTrialService(_make_config(trial_level="second"), _make_case_info(), "ev")
        send_cb = AsyncMock()
        await svc.phase_1_opening(send_cb)
        assert len(svc.transcript) >= 2

    @pytest.mark.asyncio
    async def test_phase_3_rights_notice(self):
        svc = AdversarialTrialService(_make_config(), _make_case_info(), "ev")
        send_cb = AsyncMock()
        await svc.phase_3_rights_notice(send_cb)
        roles = [t["role"] for t in svc.transcript]
        assert "judge" in roles
        assert "plaintiff" in roles
        assert "defendant" in roles

    @pytest.mark.asyncio
    async def test_phase_4_appeal_first_trial_returns_empty(self):
        svc = AdversarialTrialService(_make_config(trial_level="first"), _make_case_info(), "ev")
        send_cb = AsyncMock()
        result = await svc.phase_4_appeal(send_cb)
        assert result == ""

    @pytest.mark.asyncio
    async def test_phase_10_mediation(self):
        svc = AdversarialTrialService(_make_config(), _make_case_info(), "ev")
        send_cb = AsyncMock()
        await svc.phase_10_mediation(send_cb)
        stages = [t["stage"] for t in svc.transcript]
        assert "mediation" in stages

    @pytest.mark.asyncio
    async def test_phase_5_plaintiff_statement(self):
        config = _make_config(user_role="observer")
        svc = AdversarialTrialService(config, _make_case_info(), "ev")
        svc.plaintiff.respond = AsyncMock(return_value="plaintiff statement")
        send_cb = AsyncMock()
        result = await svc.phase_5_plaintiff_statement(send_cb)
        assert result == "plaintiff statement"


class TestAdversarialTrialServiceRecordAndSend:
    @pytest.mark.asyncio
    async def test_record_and_send(self):
        svc = AdversarialTrialService(_make_config(), _make_case_info(), "ev")
        send_cb = AsyncMock()
        await svc._record_and_send(send_cb, "judge", "test content", "opening")
        assert len(svc.transcript) == 1
        assert svc.transcript[0]["content"] == "test content"
        send_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_stage(self):
        svc = AdversarialTrialService(_make_config(), _make_case_info(), "ev")
        send_cb = AsyncMock()
        await svc._send_stage(send_cb, "opening", "Open Court")
        send_cb.assert_called_once()
        call_args = send_cb.call_args[0][0]
        assert call_args["type"] == "system_message"


class TestAdversarialTrialServiceHandleUserInput:
    @pytest.mark.asyncio
    async def test_handle_user_input_plaintiff_statement(self):
        config = _make_config(user_role="plaintiff")
        svc = AdversarialTrialService(config, _make_case_info(), "ev")
        ctx = MockTrialContext(
            session_id="s1",
            case_id=1,
            user_id=1,
            current_step=MockTrialStep.PLAINTIFF_STATEMENT,
        )
        svc.defendant.respond = AsyncMock(return_value="defendant reply")
        svc.judge.respond = AsyncMock(return_value="judge summary")
        send_cb = AsyncMock()
        set_step = AsyncMock()

        with patch.object(svc, "_continue_from_defendant", new_callable=AsyncMock) as mock_cont:
            await svc.handle_user_input(ctx, "my statement", send_cb, set_step)
            mock_cont.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_user_input_appeal(self):
        config = _make_config(user_role="plaintiff")
        svc = AdversarialTrialService(config, _make_case_info(), "ev")
        ctx = MockTrialContext(
            session_id="s1",
            case_id=1,
            user_id=1,
            current_step=MockTrialStep.APPEAL_STATEMENT,
        )
        svc.plaintiff.respond = AsyncMock(return_value="p statement")
        svc.defendant.respond = AsyncMock(return_value="d response")
        svc.judge.respond = AsyncMock(return_value="judge summary")
        send_cb = AsyncMock()
        set_step = AsyncMock()

        # Mock the continuation methods to avoid deep async chains
        svc.phase_5_plaintiff_statement = AsyncMock(return_value="p statement")
        svc.phase_6_defendant_response = AsyncMock(return_value="d response")
        with patch.object(svc, "_continue_from_defendant", new_callable=AsyncMock) as mock_cont:
            await svc.handle_user_input(ctx, "appeal input", send_cb, set_step)
            # Should have progressed to plaintiff statement
            svc.phase_5_plaintiff_statement.assert_called_once()
