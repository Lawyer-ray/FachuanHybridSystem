"""Coverage round 4: litigation consumer + mock trial consumer uncovered branches."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer
from apps.litigation_ai.consumers.mock_trial_consumer import MockTrialConsumer


# ── helpers ──

def _lit_consumer():
    c = LitigationConsumer.__new__(LitigationConsumer)
    c.session_id = None
    c.user = None
    c.session = None
    c._agent_service = None
    return c


def _mock_trial_consumer():
    c = MockTrialConsumer.__new__(MockTrialConsumer)
    c.session_id = None
    c.user = None
    c.session = None
    return c


# ============================================================
# LitigationConsumer – send_error with Exception
# ============================================================

class TestLitigationSendErrorException:
    @pytest.mark.asyncio
    async def test_exception_branch(self):
        c = _lit_consumer()
        c.send = AsyncMock()
        exc = ValueError("bad value")
        with patch("apps.core.exceptions.error_presentation.ExceptionPresenter") as MP:
            presenter = MagicMock()
            envelope = MagicMock()
            envelope.code = "VAL_ERR"
            envelope.message = "bad value"
            envelope.errors = {}
            envelope.retryable = False
            presenter.present.return_value = (envelope, None)
            MP.return_value = presenter
            with patch("apps.litigation_ai.consumers.litigation_consumer.settings") as ms:
                ms.DEBUG = False
                await c.send_error(exc)
        c.send.assert_called_once()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert payload["code"] == "VAL_ERR"
        assert payload["retryable"] is False


# ============================================================
# LitigationConsumer – handle_stop_generation
# ============================================================

class TestLitigationStopGeneration:
    @pytest.mark.asyncio
    async def test_sends_not_implemented(self):
        c = _lit_consumer()
        c.send = AsyncMock()
        await c.handle_stop_generation({})
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "停止生成" in payload["content"]


# ============================================================
# LitigationConsumer – handle_user_message empty
# ============================================================

class TestLitigationHandleUserMessageEmpty:
    @pytest.mark.asyncio
    async def test_empty_content(self):
        c = _lit_consumer()
        c.send = AsyncMock()
        await c.handle_user_message({"content": ""})
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert payload["type"] == "error"

    @pytest.mark.asyncio
    async def test_whitespace_content(self):
        c = _lit_consumer()
        c.send = AsyncMock()
        await c.handle_user_message({"content": "   "})
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert payload["type"] == "error"


# ============================================================
# LitigationConsumer – handle_select_document_type empty
# ============================================================

class TestLitigationSelectDocTypeEmpty:
    @pytest.mark.asyncio
    async def test_missing_type(self):
        c = _lit_consumer()
        c.session_id = "s1"
        c.user = MagicMock()
        c.user.id = 1
        c.session = MagicMock()
        c.session.case_id = 10
        c.send = AsyncMock()
        await c.handle_select_document_type({"document_type": ""})
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert "缺少" in payload["message"]


# ============================================================
# LitigationConsumer – agent_service cached
# ============================================================

class TestLitigationAgentServiceCached:
    def test_cached(self):
        c = _lit_consumer()
        mock_svc = MagicMock()
        c._agent_service = mock_svc
        assert c.agent_service is mock_svc


# ============================================================
# LitigationConsumer – _handle_agent_error
# ============================================================

class TestLitigationHandleAgentError:
    @pytest.mark.asyncio
    async def test_delegates_to_send_error(self):
        c = _lit_consumer()
        c.send = AsyncMock()
        exc = RuntimeError("agent fail")
        with patch("apps.core.exceptions.error_presentation.ExceptionPresenter") as MP:
            presenter = MagicMock()
            envelope = MagicMock()
            envelope.code = "ERR"
            envelope.message = "agent fail"
            envelope.errors = {}
            envelope.retryable = False
            presenter.present.return_value = (envelope, None)
            MP.return_value = presenter
            with patch("apps.litigation_ai.consumers.litigation_consumer.settings") as ms:
                ms.DEBUG = False
                await c._handle_agent_error(exc)
        c.send.assert_called_once()


# ============================================================
# LitigationConsumer – _handle_select_evidence_agent
# ============================================================

class TestLitigationHandleSelectEvidenceAgent:
    @pytest.mark.asyncio
    async def test_success(self):
        c = _lit_consumer()
        c.session_id = "s1"
        c.session = MagicMock()
        c.session.case_id = 10
        c.send = AsyncMock()
        mock_agent = MagicMock()
        mock_agent.handle_evidence_selection = AsyncMock(return_value={"type": "result"})
        c._agent_service = mock_agent
        await c._handle_select_evidence_agent([1], [2], [3])
        mock_agent.handle_evidence_selection.assert_called_once()
        c.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_path(self):
        c = _lit_consumer()
        c.session_id = "s1"
        c.session = MagicMock()
        c.session.case_id = 10
        c.send = AsyncMock()
        mock_agent = MagicMock()
        mock_agent.handle_evidence_selection = AsyncMock(side_effect=RuntimeError("fail"))
        c._agent_service = mock_agent
        with patch("apps.core.exceptions.error_presentation.ExceptionPresenter") as MP:
            presenter = MagicMock()
            envelope = MagicMock()
            envelope.code = "ERR"
            envelope.message = "fail"
            envelope.errors = {}
            envelope.retryable = False
            presenter.present.return_value = (envelope, None)
            MP.return_value = presenter
            with patch("apps.litigation_ai.consumers.litigation_consumer.settings") as ms:
                ms.DEBUG = False
                await c._handle_select_evidence_agent([1], [2], [3])
        c.send.assert_called_once()


# ============================================================
# MockTrialConsumer – _send_error Exception branch
# ============================================================

class TestMockTrialSendErrorException:
    @pytest.mark.asyncio
    async def test_exception_branch(self):
        c = _mock_trial_consumer()
        c.send = AsyncMock()
        exc = RuntimeError("boom")
        with patch("apps.core.exceptions.error_presentation.ExceptionPresenter") as MP:
            presenter = MagicMock()
            envelope = MagicMock()
            envelope.code = "RT_ERR"
            envelope.message = "boom"
            envelope.errors = {}
            envelope.retryable = True
            presenter.present.return_value = (envelope, None)
            MP.return_value = presenter
            with patch("apps.litigation_ai.consumers.mock_trial_consumer.settings") as ms:
                ms.DEBUG = False
                await c._send_error(exc)
        c.send.assert_called_once()
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert payload["code"] == "RT_ERR"
        assert payload["retryable"] is True


# ============================================================
# MockTrialConsumer – disconnect variations
# ============================================================

class TestMockTrialDisconnect:
    @pytest.mark.asyncio
    async def test_no_session_id(self):
        c = _mock_trial_consumer()
        c.session_id = None
        c.channel_layer = AsyncMock()
        await c.disconnect(1000)
        c.channel_layer.group_discard.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_session_id(self):
        c = _mock_trial_consumer()
        c.session_id = "s1"
        c.channel_layer = AsyncMock()
        c.channel_name = "ch"
        await c.disconnect(1000)
        c.channel_layer.group_discard.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_in_group_discard(self):
        c = _mock_trial_consumer()
        c.session_id = "s1"
        c.channel_layer = AsyncMock()
        c.channel_layer.group_discard.side_effect = RuntimeError("fail")
        c.channel_name = "ch"
        await c.disconnect(1000)


# ============================================================
# MockTrialConsumer – _handle_user_message empty/summary
# ============================================================

class TestMockTrialUserMessageVariations:
    @pytest.mark.asyncio
    async def test_empty_content(self):
        c = _mock_trial_consumer()
        c.send = AsyncMock()
        await c._handle_user_message({"content": ""})
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert payload["type"] == "error"

    @pytest.mark.asyncio
    async def test_none_content(self):
        c = _mock_trial_consumer()
        c.send = AsyncMock()
        await c._handle_user_message({"content": None})
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert payload["type"] == "error"


# ============================================================
# MockTrialConsumer – _handle_set_difficulty
# ============================================================

class TestMockTrialSetDifficulty:
    @pytest.mark.asyncio
    async def test_invalid_difficulty(self):
        c = _mock_trial_consumer()
        c.send = AsyncMock()
        await c._handle_set_difficulty({"difficulty": "extreme"})
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert payload["type"] == "error"

    @pytest.mark.asyncio
    async def test_valid_difficulty(self):
        c = _mock_trial_consumer()
        c.session_id = "s1"
        c.send = AsyncMock()
        with patch("apps.litigation_ai.services.flow.session_repository.LitigationSessionRepository") as MR:
            repo = MagicMock()
            repo.update_metadata = AsyncMock()
            MR.return_value = repo
            await c._handle_set_difficulty({"difficulty": "hard"})
            repo.update_metadata.assert_called_once_with("s1", {"debate_difficulty": "hard"})


# ============================================================
# MockTrialConsumer – _handle_select_mode empty
# ============================================================

class TestMockTrialSelectModeEmpty:
    @pytest.mark.asyncio
    async def test_missing_mode(self):
        c = _mock_trial_consumer()
        c.send = AsyncMock()
        await c._handle_select_mode({"mode": ""})
        payload = json.loads(c.send.call_args[1]["text_data"])
        assert payload["type"] == "error"


# ============================================================
# MockTrialConsumer – _handle_skip_evidence / _handle_end_debate
# ============================================================

class TestMockTrialSkipAndEndDebate:
    @pytest.mark.asyncio
    async def test_skip_evidence_adds_message(self):
        c = _mock_trial_consumer()
        c.session_id = "s1"
        c.user = MagicMock()
        c.user.id = 1
        c.session = MagicMock()
        c.session.case_id = 10
        c.send = AsyncMock()
        with patch.object(c, '_add_message', new_callable=AsyncMock) as mock_add:
            with patch("apps.litigation_ai.services.mock_trial.mock_trial_flow_service.MockTrialFlowService") as MF:
                flow = MagicMock()
                flow.handle_simulation = AsyncMock()
                MF.return_value = flow
                await c._handle_skip_evidence({})
                mock_add.assert_called_once_with("user", "跳过剩余证据")

    @pytest.mark.asyncio
    async def test_end_debate_adds_message(self):
        c = _mock_trial_consumer()
        c.session_id = "s1"
        c.user = MagicMock()
        c.user.id = 1
        c.session = MagicMock()
        c.session.case_id = 10
        c.send = AsyncMock()
        with patch.object(c, '_add_message', new_callable=AsyncMock) as mock_add:
            with patch("apps.litigation_ai.services.mock_trial.mock_trial_flow_service.MockTrialFlowService") as MF:
                flow = MagicMock()
                flow.handle_simulation = AsyncMock()
                MF.return_value = flow
                await c._handle_end_debate({})
                mock_add.assert_called_once_with("user", "结束辩论")
