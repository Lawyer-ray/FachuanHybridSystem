"""Coverage round 4: reminder_service_adapter + story_viz job_service + image_rotation job_service."""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import ValidationException, NotFoundError


# ============================================================
# reminder_service_adapter.py
# ============================================================

class TestReminderServiceAdapter:
    def _make_adapter(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter.__new__(ReminderServiceAdapter)
        adapter._contract_target_query = None
        adapter._case_target_query = None
        adapter._case_log_target_query = None
        return adapter

    def test_create_reminder_internal_invalid_type(self):
        adapter = self._make_adapter()
        result = adapter.create_reminder_internal(1, "invalid_type", datetime.now())
        assert result is None

    def test_create_reminder_internal_none_time(self):
        adapter = self._make_adapter()
        from apps.reminders.models import ReminderType
        result = adapter.create_reminder_internal(1, ReminderType.values[0], None)
        assert result is None

    def test_get_reminder_type_by_code_invalid(self):
        adapter = self._make_adapter()
        result = adapter.get_reminder_type_by_code_internal("nonexistent_code")
        assert result is None

    def test_get_reminder_type_for_document_unknown(self):
        adapter = self._make_adapter()
        result = adapter.get_reminder_type_for_document_internal("unknown_doc_type")
        assert result is None

    def test_get_reminder_type_for_document_known(self):
        adapter = self._make_adapter()
        result = adapter.get_reminder_type_for_document_internal("court_summons")
        assert result is not None
        assert result.code == "hearing"

    def test_enrich_export_row_valid_type(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        from apps.reminders.models import ReminderType
        row = {"reminder_type": ReminderType.values[0], "content": "test"}
        result = ReminderServiceAdapter._enrich_export_row(row)
        assert "reminder_type_label" in result

    def test_enrich_export_row_invalid_type(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        row = {"reminder_type": "bad_type", "content": "test"}
        result = ReminderServiceAdapter._enrich_export_row(row)
        assert result["reminder_type_label"] == "bad_type"

    def test_get_preferred_case_log_reminder_no_reminders(self):
        adapter = self._make_adapter()
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value = []
            result = adapter._get_preferred_case_log_reminder(case_log_id=1)
        assert result is None

    def test_get_preferred_case_log_reminder_with_source(self):
        adapter = self._make_adapter()
        reminder = MagicMock()
        reminder.metadata = {"source": "test_source"}
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value = [reminder]
            result = adapter._get_preferred_case_log_reminder(case_log_id=1, metadata_source="test_source")
        assert result is reminder

    def test_get_preferred_case_log_reminder_source_not_found(self):
        adapter = self._make_adapter()
        reminder = MagicMock()
        reminder.metadata = {"source": "other"}
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value = [reminder]
            result = adapter._get_preferred_case_log_reminder(case_log_id=1, metadata_source="missing_source")
        assert result is None

    def test_get_preferred_case_log_reminder_no_source_returns_first(self):
        adapter = self._make_adapter()
        reminder = MagicMock()
        reminder.metadata = {}
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value = [reminder]
            result = adapter._get_preferred_case_log_reminder(case_log_id=1)
        assert result is reminder

    def test_clear_case_log_reminder_no_match(self):
        adapter = self._make_adapter()
        with patch.object(adapter, '_get_preferred_case_log_reminder', return_value=None):
            assert adapter.clear_case_log_reminder_internal(case_log_id=1) is False

    def test_clear_case_log_reminder_found(self):
        adapter = self._make_adapter()
        reminder = MagicMock()
        with patch.object(adapter, '_get_preferred_case_log_reminder', return_value=reminder):
            with patch.object(type(adapter).__bases__[0], 'delete_reminder') as mock_del:
                result = adapter.clear_case_log_reminder_internal(case_log_id=1)
        assert result is True

    def test_export_case_log_reminders_batch_empty(self):
        adapter = self._make_adapter()
        result = adapter.export_case_log_reminders_batch_internal(case_log_ids=[])
        assert result == {}

    def test_get_latest_case_log_reminder_found(self):
        adapter = self._make_adapter()
        row = {"id": 1, "reminder_type": "hearing", "content": "test"}
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value.values.return_value.first.return_value = row
            result = adapter.get_latest_case_log_reminder_internal(case_log_id=1)
        assert result is not None

    def test_get_latest_case_log_reminder_not_found(self):
        adapter = self._make_adapter()
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value.values.return_value.first.return_value = None
            result = adapter.get_latest_case_log_reminder_internal(case_log_id=1)
        assert result is None

    def test_document_type_mapping(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        assert ReminderServiceAdapter.DOCUMENT_TYPE_TO_REMINDER_TYPE["court_summons"] == "hearing"
        assert ReminderServiceAdapter.DOCUMENT_TYPE_TO_REMINDER_TYPE["verdict"] == "appeal_deadline"
        assert ReminderServiceAdapter.DOCUMENT_TYPE_TO_REMINDER_TYPE["asset_preservation"] == "asset_preservation_expires"


# ============================================================
# story_viz/services/job_service.py
# ============================================================

class TestStoryAnimationJobService:
    def _make_service(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        return StoryAnimationJobService()

    def test_stage_index_known(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        assert StoryAnimationJobService._stage_index("extracting_facts") >= 0
        assert StoryAnimationJobService._stage_index("composing_html") >= 0

    def test_stage_index_unknown(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        assert StoryAnimationJobService._stage_index("nonexistent") == -1

    def test_summarize_facts(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        facts = {
            "parties": [{"name": "A", "role": "plaintiff"}],
            "events": [{"sequence": 1, "time_label": "2024", "summary": "event1"}],
            "relationships": [{"source": "A", "target": "B", "relation_type": "opponent"}],
        }
        result = StoryAnimationJobService._summarize_facts(facts)
        assert len(result["parties"]) == 1
        assert len(result["events"]) == 1
        assert len(result["relationships"]) == 1

    def test_summarize_facts_empty(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        result = StoryAnimationJobService._summarize_facts({})
        assert result["parties"] == []
        assert result["events"] == []

    def test_summarize_facts_non_list(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        result = StoryAnimationJobService._summarize_facts({"parties": "not_list", "events": 123})
        assert result["parties"] == []
        assert result["events"] == []

    def test_summarize_script(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        script = {
            "timeline_nodes": [1, 2],
            "relationship_nodes": [3],
            "edges": [4, 5, 6],
            "highlights": ["h1", "h2"],
            "annotations": ["a1"],
        }
        result = StoryAnimationJobService._summarize_script(script)
        assert result["timeline_nodes_count"] == 2
        assert result["edges_count"] == 3

    def test_summarize_script_non_list(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        result = StoryAnimationJobService._summarize_script({"timeline_nodes": "not_list"})
        assert result["timeline_nodes_count"] == 0

    def test_summarize_render(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        result = StoryAnimationJobService._summarize_render({"nodes": [1, 2], "edges": [3]})
        assert result["node_count"] == 2
        assert result["edge_count"] == 1

    def test_summarize_render_non_list(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        result = StoryAnimationJobService._summarize_render({"nodes": "not_list"})
        assert result["node_count"] == 0

    def test_build_suggested_questions(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        facts = {
            "parties": [{"name": "A"}],
            "events": [{"summary": "e1", "amounts": [100]}],
            "relationships": [{"source": "A"}],
            "judgment_result": "胜诉",
        }
        result = StoryAnimationJobService._build_suggested_questions(facts=facts)
        assert len(result) > 0
        assert any("当事人" in q for q in result)
        assert any("金额" in q for q in result)

    def test_build_suggested_questions_empty(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        result = StoryAnimationJobService._build_suggested_questions(facts={})
        assert result == []

    def test_build_status_payload(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus
        anim = MagicMock()
        anim.id = uuid.uuid4()
        anim.status = StoryAnimationStatus.COMPLETED
        anim.source_title = "Title"
        anim.viz_type = "timeline"
        anim.current_stage = "composing_html"
        anim.get_current_stage_display.return_value = "组装HTML"
        anim.progress_percent = 100
        anim.error_message = ""
        anim.task_id = "task1"
        anim.cancel_requested = False
        anim.facts_payload = {"parties": [{"name": "A"}], "events": [], "relationships": []}
        anim.created_at = datetime.now()
        anim.started_at = datetime.now()
        anim.finished_at = datetime.now()
        anim.updated_at = datetime.now()
        result = svc.build_status_payload(animation=anim)
        assert result["status"] == StoryAnimationStatus.COMPLETED
        assert result["preview_url"] != ""
        assert result["parties_count"] == 1

    def test_build_status_payload_not_completed(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus
        anim = MagicMock()
        anim.id = uuid.uuid4()
        anim.status = StoryAnimationStatus.PENDING
        anim.source_title = "Title"
        anim.viz_type = "timeline"
        anim.current_stage = "queued"
        anim.get_current_stage_display.return_value = "排队中"
        anim.progress_percent = 0
        anim.error_message = ""
        anim.task_id = ""
        anim.cancel_requested = False
        anim.facts_payload = None
        anim.created_at = datetime.now()
        anim.started_at = None
        anim.finished_at = None
        anim.updated_at = datetime.now()
        result = svc.build_status_payload(animation=anim)
        assert result["preview_url"] == ""

    def test_build_preview_payload_completed(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus
        anim = MagicMock()
        anim.id = uuid.uuid4()
        anim.status = StoryAnimationStatus.COMPLETED
        anim.animation_html = "<html></html>"
        result = svc.build_preview_payload(animation=anim)
        assert result["has_html"] is True
        assert result["animation_html"] == "<html></html>"

    def test_build_preview_payload_not_completed(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus
        anim = MagicMock()
        anim.id = uuid.uuid4()
        anim.status = StoryAnimationStatus.PENDING
        anim.animation_html = "<html></html>"
        result = svc.build_preview_payload(animation=anim)
        assert result["animation_html"] == ""

    def test_build_stages_completed(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus, StoryAnimationStage
        anim = MagicMock()
        anim.status = StoryAnimationStatus.COMPLETED
        anim.current_stage = StoryAnimationStage.COMPOSING_HTML
        anim.facts_payload = {"parties": [], "events": []}
        stages = svc._build_stages(animation=anim)
        assert all(s["status"] == "done" for s in stages)

    def test_build_stages_processing_active(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus, StoryAnimationStage
        anim = MagicMock()
        anim.status = StoryAnimationStatus.PROCESSING
        anim.current_stage = StoryAnimationStage.DIRECTING_SCRIPT
        anim.facts_payload = {}
        stages = svc._build_stages(animation=anim)
        active = [s for s in stages if s["status"] == "active"]
        assert len(active) == 1

    def test_build_stages_failed(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus, StoryAnimationStage
        anim = MagicMock()
        anim.status = StoryAnimationStatus.FAILED
        anim.current_stage = StoryAnimationStage.RENDERING_LAYOUT
        anim.facts_payload = {}
        stages = svc._build_stages(animation=anim)
        failed = [s for s in stages if s["status"] == "failed"]
        assert len(failed) == 1

    def test_build_stages_cancelled(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus, StoryAnimationStage
        anim = MagicMock()
        anim.status = StoryAnimationStatus.CANCELLED
        anim.current_stage = StoryAnimationStage.EXTRACTING_FACTS
        anim.facts_payload = {"parties": [{"name": "A"}], "events": [{"sequence": 1, "time_label": "t", "summary": "s"}]}
        stages = svc._build_stages(animation=anim)
        cancelled = [s for s in stages if s["status"] == "cancelled"]
        assert len(cancelled) == 1

    def test_build_detail_payload(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus
        anim = MagicMock()
        anim.id = uuid.uuid4()
        anim.status = StoryAnimationStatus.COMPLETED
        anim.source_title = "Title"
        anim.viz_type = "timeline"
        anim.current_stage = "composing_html"
        anim.get_current_stage_display.return_value = "组装HTML"
        anim.progress_percent = 100
        anim.error_message = ""
        anim.task_id = "task1"
        anim.cancel_requested = False
        anim.facts_payload = {"parties": [], "events": [], "relationships": []}
        anim.script_payload = {"timeline_nodes": [], "edges": []}
        anim.render_payload = {"nodes": [], "edges": []}
        anim.animation_html = "<html></html>"
        anim.created_at = datetime.now()
        anim.started_at = datetime.now()
        anim.finished_at = datetime.now()
        anim.updated_at = datetime.now()
        result = svc.build_detail_payload(animation=anim)
        assert "stages" in result
        assert "facts_summary" in result
        assert "has_html" in result
        assert result["has_html"] is True

    def test_get_animation_not_found(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimation
        with patch.object(StoryAnimation.objects, 'get', side_effect=StoryAnimation.DoesNotExist()):
            with pytest.raises(NotFoundError):
                svc.get_animation(animation_id=uuid.uuid4())

    def test_ask_not_completed(self):
        svc = self._make_service()
        from apps.story_viz.models import StoryAnimationStatus
        anim = MagicMock()
        anim.status = StoryAnimationStatus.PENDING
        with patch.object(svc, 'get_animation', return_value=anim):
            with pytest.raises(ValidationException, match="未完成"):
                svc.ask(animation_id=uuid.uuid4(), question="what?")


# ============================================================
# image_rotation/services/job_service.py
# ============================================================

class TestImageRotationJobService:
    def test_guess_ext(self):
        from apps.image_rotation.services.job_service import _guess_ext
        assert _guess_ext("photo.jpg") == ".jpg"
        assert _guess_ext("photo.JPEG") == ".jpeg"
        assert _guess_ext("photo.png") == ".png"
        assert _guess_ext("photo.webp") == ".webp"
        assert _guess_ext("photo.tiff") == ".tiff"
        assert _guess_ext("photo.bmp") == ".bmp"
        assert _guess_ext("photo.gif") == ".gif"
        assert _guess_ext("noext") == ".jpg"
        assert _guess_ext("photo.xyz") == ".jpg"

    def test_create_job_mismatch_raises(self):
        from apps.image_rotation.services.job_service import ImageRotationJobService
        # Unwrap the @transaction.atomic decorator for testing (avoids DB access)
        original_func = ImageRotationJobService.create_job.__wrapped__
        with pytest.raises(ValueError, match="数量不匹配"):
            original_func(
                name="test",
                pages_meta=[{"filename": "a.jpg"}],
                source_files=[MagicMock(), MagicMock()],
            )

    def test_get_job_not_found(self):
        from apps.image_rotation.services.job_service import ImageRotationJobService
        from apps.image_rotation.models import ImageRotationJob
        with patch.object(ImageRotationJob.objects, 'get', side_effect=ImageRotationJob.DoesNotExist()):
            with pytest.raises(NotFoundError):
                ImageRotationJobService.get_job(uuid.uuid4())

    def test_list_jobs_default(self):
        from apps.image_rotation.services.job_service import ImageRotationJobService
        with patch("apps.image_rotation.services.job_service.ImageRotationJob") as MockJob:
            MockJob.objects.all.return_value.count.return_value = 0
            MockJob.objects.all.return_value.__getitem__ = MagicMock(return_value=[])
            result = ImageRotationJobService.list_jobs()
        assert result["total_count"] == 0
        assert result["page"] == 1

    def test_list_jobs_with_user(self):
        from apps.image_rotation.services.job_service import ImageRotationJobService
        user = MagicMock()
        with patch("apps.image_rotation.services.job_service.ImageRotationJob") as MockJob:
            qs = MagicMock()
            qs.count.return_value = 0
            qs.__getitem__ = MagicMock(return_value=[])
            MockJob.objects.all.return_value = qs
            qs.filter.return_value = qs
            result = ImageRotationJobService.list_jobs(created_by=user)
        assert result["total_count"] == 0

    def test_delete_job(self):
        from apps.image_rotation.services.job_service import ImageRotationJobService
        mock_job = MagicMock()
        with patch.object(ImageRotationJobService, 'get_job', return_value=mock_job):
            ImageRotationJobService.delete_job(uuid.uuid4())
        mock_job.delete.assert_called_once()
