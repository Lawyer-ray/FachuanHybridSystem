"""litigation_ai app Model 单元测试

覆盖 LitigationSession 的 property、choices。
"""

import pytest

from apps.litigation_ai.models.choices import DocumentType, MockTrialMode, SessionStatus, SessionType
from apps.litigation_ai.models.session import LitigationSession
from apps.testing.factories import CaseFactory, LawyerFactory


# ============================================================
# LitigationSession
# ============================================================


@pytest.mark.django_db
class TestLitigationSession:
    def test_session_id_short(self):
        case = CaseFactory()
        session = LitigationSession.objects.create(case=case)
        assert len(session.session_id_short) == 8
        assert session.session_id_short == str(session.session_id)[:8]

    def test_litigation_goal_default(self):
        case = CaseFactory()
        session = LitigationSession.objects.create(case=case, metadata={})
        assert session.litigation_goal == ""

    def test_litigation_goal_with_value(self):
        case = CaseFactory()
        session = LitigationSession.objects.create(
            case=case,
            metadata={"litigation_goal": "请求判令被告偿还借款100万元"},
        )
        assert session.litigation_goal == "请求判令被告偿还借款100万元"

    def test_evidence_list_ids_default(self):
        case = CaseFactory()
        session = LitigationSession.objects.create(case=case, metadata={})
        assert session.evidence_list_ids == []

    def test_evidence_list_ids_with_values(self):
        case = CaseFactory()
        session = LitigationSession.objects.create(
            case=case,
            metadata={"evidence_list_ids": [1, 2, 3]},
        )
        assert session.evidence_list_ids == [1, 2, 3]

    def test_evidence_list_ids_non_list(self):
        """metadata 中 evidence_list_ids 不是 list 时应返回空列表"""
        case = CaseFactory()
        session = LitigationSession.objects.create(
            case=case,
            metadata={"evidence_list_ids": "invalid"},
        )
        assert session.evidence_list_ids == []

    def test_total_tokens_default(self):
        case = CaseFactory()
        session = LitigationSession.objects.create(case=case, metadata={})
        assert session.total_tokens == 0

    def test_total_tokens_with_value(self):
        case = CaseFactory()
        session = LitigationSession.objects.create(
            case=case,
            metadata={"total_tokens": 1500},
        )
        assert session.total_tokens == 1500

    def test_total_tokens_non_int(self):
        """metadata 中 total_tokens 不是 int 时应返回 0"""
        case = CaseFactory()
        session = LitigationSession.objects.create(
            case=case,
            metadata={"total_tokens": "abc"},
        )
        assert session.total_tokens == 0

    def test_model_name_default(self):
        case = CaseFactory()
        session = LitigationSession.objects.create(case=case, metadata={})
        assert session.model_name == ""

    def test_model_name_with_value(self):
        case = CaseFactory()
        session = LitigationSession.objects.create(
            case=case,
            metadata={"model": "gpt-4"},
        )
        assert session.model_name == "gpt-4"

    def test_metadata_none(self):
        """metadata 为 None 时 property 不应报错"""
        case = CaseFactory()
        session = LitigationSession(case=case, metadata=None)
        assert session.litigation_goal == ""
        assert session.evidence_list_ids == []
        assert session.total_tokens == 0
        assert session.model_name == ""


# ============================================================
# Choices
# ============================================================


@pytest.mark.django_db
class TestLitigationChoices:
    def test_document_type_choices(self):
        assert DocumentType.COMPLAINT.value == "complaint"
        assert DocumentType.DEFENSE.value == "defense"
        assert DocumentType.COUNTERCLAIM.value == "counterclaim"

    def test_session_status_choices(self):
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.CANCELLED.value == "cancelled"

    def test_session_type_choices(self):
        assert SessionType.DOC_GEN.value == "doc_gen"
        assert SessionType.MOCK_TRIAL.value == "mock_trial"

    def test_mock_trial_mode_choices(self):
        assert MockTrialMode.JUDGE.value == "judge"
        assert MockTrialMode.CROSS_EXAM.value == "cross_exam"
        assert MockTrialMode.DEBATE.value == "debate"
        assert MockTrialMode.ADVERSARIAL.value == "adversarial"

    def test_message_role_choices(self):
        from apps.litigation_ai.models.choices import MessageRole

        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.SYSTEM.value == "system"
