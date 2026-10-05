"""client/adapters/admin_adapters.py 单元测试。

覆盖 GsxtReportAdapter（任务创建/登录启动/等待任务/报告上传/状态选项）
与 CredentialAdapter（凭证选择排序）。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask
from apps.client.adapters.admin_adapters import CredentialAdapter, GsxtReportAdapter
from apps.organization.models import AccountCredential
from apps.testing.factories import ClientFactory, LawyerFactory


@pytest.mark.django_db
class TestGsxtReportAdapterCreate:
    def test_creates_task_waiting_captcha(self) -> None:
        client = ClientFactory(name="甲公司")
        task_id = GsxtReportAdapter().create_report_task(client.pk, "甲公司", "91330000XXX")
        task = GsxtReportTask.objects.get(pk=task_id)
        assert task.client_id == client.pk
        assert task.company_name == "甲公司"
        assert task.credit_code == "91330000XXX"
        assert task.status == GsxtReportStatus.WAITING_CAPTCHA


@pytest.mark.django_db
class TestGsxtReportAdapterLogin:
    def test_start_login_invokes_service(self) -> None:
        lawyer = LawyerFactory(username="gsxt-user")
        credential = AccountCredential.objects.create(
            lawyer=lawyer, site_name="一张网", account="acc", password="p"
        )
        with patch("apps.automation.services.gsxt.gsxt_login_service.start_login_gsxt") as mock_start:
            GsxtReportAdapter().start_login(credential.pk, task_id=55)

        mock_start.assert_called_once()
        passed_credential, passed_task_id = mock_start.call_args.args
        assert passed_credential.pk == credential.pk
        assert passed_task_id == 55


@pytest.mark.django_db
class TestGsxtReportAdapterWaitingTask:
    def test_returns_waiting_email_task(self) -> None:
        client = ClientFactory(name="乙公司")
        waiting = GsxtReportTask.objects.create(
            client=client, company_name="乙公司", status=GsxtReportStatus.WAITING_EMAIL
        )
        GsxtReportTask.objects.create(client=client, company_name="乙公司-2", status=GsxtReportStatus.WAITING_CAPTCHA)

        result = GsxtReportAdapter().get_waiting_email_task(client.pk)

        assert result is not None
        assert result.pk == waiting.pk

    def test_returns_none_when_no_waiting(self) -> None:
        client = ClientFactory(name="丙公司")
        GsxtReportTask.objects.create(client=client, company_name="丙公司", status=GsxtReportStatus.WAITING_CAPTCHA)
        assert GsxtReportAdapter().get_waiting_email_task(client.pk) is None


@pytest.mark.django_db
class TestGsxtReportAdapterUpload:
    def test_upload_success(self) -> None:
        client = ClientFactory(name="丁公司")
        task = GsxtReportTask.objects.create(
            client=client, company_name="丁公司", status=GsxtReportStatus.WAITING_EMAIL
        )

        with patch("django.db.models.fields.files.FieldFile.save") as mock_file_save:
            result = GsxtReportAdapter().upload_report(task.pk, b"pdf-bytes", "丁公司报告.pdf")

        assert result is True
        mock_file_save.assert_called_once()
        task.refresh_from_db()
        assert task.status == GsxtReportStatus.SUCCESS

    def test_upload_missing_task_returns_false(self) -> None:
        assert GsxtReportAdapter().upload_report(99999, b"x", "a.pdf") is False


class TestGsxtReportAdapterStatusChoices:
    def test_returns_enum_choices(self) -> None:
        choices = GsxtReportAdapter().get_task_status_choices()
        assert (GsxtReportStatus.WAITING_CAPTCHA, "等待验证码") in choices


@pytest.mark.django_db
class TestCredentialAdapter:
    def test_no_credential_returns_none(self) -> None:
        assert CredentialAdapter().get_gsxt_credential() is None

    def test_prefers_recent_success(self) -> None:
        """两条凭证都有成功记录时，最近成功者优先于成功次数。"""
        lawyer = LawyerFactory(username="cred-order-user")
        older = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="国家企业信用信息公示系统",
            account="old",
            password="p",
            login_success_count=10,
            last_login_success_at=timezone.now() - timezone.timedelta(days=30),
        )
        newer = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="国家企业信用信息公示系统",
            account="new",
            password="p",
            login_success_count=1,
            last_login_success_at=timezone.now(),
        )
        unrelated = AccountCredential.objects.create(lawyer=lawyer, site_name="一张网", account="other", password="p")
        assert unrelated.pk != older.pk

        result = CredentialAdapter().get_gsxt_credential()

        assert result is not None
        assert result.pk == newer.pk
        assert result.pk != older.pk

    def test_falls_back_to_success_count(self) -> None:
        """无最近登录时间时按成功次数降序选择。"""
        lawyer = LawyerFactory(username="cred-count-user")
        low = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="国家企业信用信息公示系统",
            account="low",
            password="p",
            login_success_count=2,
        )
        high = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="国家企业信用公示系统",  # icountains 命中
            account="high",
            password="p",
            login_success_count=9,
        )
        assert low.pk != high.pk

        result = CredentialAdapter().get_gsxt_credential()

        assert result is not None
        assert result.pk == high.pk
