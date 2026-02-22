import pytest
from django.db import connection

from apps.core.models import ConversationHistory
from apps.documents.models import GenerationTask
from apps.litigation_ai.models import LitigationSession
from apps.litigation_ai.services.conversation_service import ConversationService
from tests.factories.case_factories import CaseFactory
from tests.factories.organization_factories import LawyerFactory


@pytest.mark.django_db
def test_delete_session_cleans_related_rows():
    case = CaseFactory()
    lawyer = LawyerFactory()
    session = LitigationSession.objects.create(case=case, user=lawyer, status="active", metadata={})  # type: ignore[misc]

    ConversationHistory.objects.create(
        session_id=str(session.session_id),
        user_id=str(lawyer.id),  # type: ignore[attr-defined]
        role="user",
        content="hi",
        metadata={},
        litigation_session=session,
        step="init",
    )
    task = GenerationTask.objects.create(  # type: ignore[misc]
        case=case,
        litigation_session=session,
        generation_method="ai",
        document_type="起诉状",
        metadata={},
    )

    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_litigationmessage';")
        if cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO documents_litigationmessage (role, content, metadata, created_at, session_id)
                VALUES ('user', 'legacy msg', '{}', datetime('now'), %s)
                """,
                [session.id],
            )

    ConversationService().delete_session(str(session.session_id), user=lawyer)

    assert not LitigationSession.objects.filter(id=session.id).exists()
    assert ConversationHistory.objects.filter(litigation_session_id=session.id).count() == 0
    assert ConversationHistory.objects.filter(session_id=str(session.session_id)).count() == 1
    task.refresh_from_db()
    assert task.litigation_session_id is None
