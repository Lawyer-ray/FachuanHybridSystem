import pytest

from apps.chat_records.models import ChatRecordExportTask, ChatRecordProject, ExportType
from apps.chat_records.services.export_task_service import ExportTaskService
from apps.chat_records.services.project_service import ProjectService
from apps.core.exceptions import PermissionDenied
from apps.core.tasking import TaskSubmissionService
from apps.organization.models.lawyer import Lawyer


@pytest.mark.django_db
def test_chat_records_project_access_is_scoped_to_creator():
    u1 = Lawyer.objects.create_user(username="u1", password="x")
    u2 = Lawyer.objects.create_user(username="u2", password="x")
    project = ChatRecordProject.objects.create(name="p1", description="", created_by=u1)

    svc = ProjectService()
    assert list(svc.list_projects(user=u1))
    assert list(svc.list_projects(user=u2)) == []

    with pytest.raises(PermissionDenied):
        svc.get_project(user=u2, project_id=project.id)


@pytest.mark.django_db
def test_chat_records_export_task_access_is_scoped_to_project():
    u1 = Lawyer.objects.create_user(username="u1", password="x")
    u2 = Lawyer.objects.create_user(username="u2", password="x")
    project = ChatRecordProject.objects.create(name="p1", description="", created_by=u1)
    task = ChatRecordExportTask.objects.create(project=project, export_type=ExportType.PDF, layout={})

    fake_submitter = TaskSubmissionService()
    service = ExportTaskService(task_submission_service=fake_submitter)  # type: ignore[call-arg]

    assert service.get_task(user=u1, task_id=str(task.id)).id == task.id
    with pytest.raises(PermissionDenied):
        service.get_task(user=u2, task_id=str(task.id))
