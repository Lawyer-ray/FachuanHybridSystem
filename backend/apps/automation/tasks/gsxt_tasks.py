"""国家企业信用信息公示系统相关 Django-Q 任务函数。"""

from __future__ import annotations

import logging
from datetime import timedelta
from importlib import import_module

from django.apps import apps as django_apps
from django.utils import timezone

logger = logging.getLogger("apps.automation")

# 报告邮件轮询上限：60 秒/次 × 30 次 ≈ 30 分钟，超时仍未收到邮件即终止任务，
# 避免无限续期 schedule 导致的永久轮询
REPORT_EMAIL_POLL_TIMEOUT = timedelta(minutes=30)


def check_gsxt_report_email(task_id: int, company_name: str) -> None:
    """
    Django-Q 任务：检查邮箱是否收到企业信用报告，收到则保存为营业执照附件。
    未收到时重新入队（60秒后再试），直到任务状态不再是 WAITING_EMAIL 为止；
    轮询超过 REPORT_EMAIL_POLL_TIMEOUT 仍未收到则标记 FAILED，不再续期。
    """
    from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask
    from apps.automation.services.gsxt.gsxt_email_service import EMAIL_CREDENTIAL_ID, _fetch_report_attachment
    from apps.core.tasking import ScheduleQueryService

    task = GsxtReportTask.objects.select_related("client").get(pk=task_id)

    # 任务已终态，不再重试
    if task.status not in (GsxtReportStatus.WAITING_EMAIL,):
        return

    account_credential_model = django_apps.get_model("organization", "AccountCredential")
    cred = account_credential_model.objects.get(pk=EMAIL_CREDENTIAL_ID)
    pdf_bytes = _fetch_report_attachment(cred.account, cred.password, company_name)

    if pdf_bytes:
        client = task.client
        rel_path = f"client_docs/{client.pk}/{company_name[:20]}_企业信用报告.pdf"
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        default_storage.save(rel_path, ContentFile(pdf_bytes))

        identity_doc_service_cls = import_module(
            "apps.client.services.client_identity_doc_service"
        ).ClientIdentityDocService
        identity_doc_service_cls().upsert_identity_doc_file(
            client_id=client.pk,
            doc_type="business_license",
            file_path=str(rel_path),
        )

        task.status = GsxtReportStatus.SUCCESS
        task.error_message = ""
        task.save(update_fields=["status", "error_message"])
        logger.info("任务 %d：报告已保存为营业执照附件，client_id=%d", task_id, client.pk)
    elif timezone.now() - task.created_at >= REPORT_EMAIL_POLL_TIMEOUT:
        # 轮询达到上限：标记失败并写明原因，不再续期 schedule
        task.status = GsxtReportStatus.FAILED
        task.error_message = (
            f"报告邮件未到达：已轮询{int(REPORT_EMAIL_POLL_TIMEOUT.total_seconds() / 60)}分钟"
            "仍未收到企业信用报告邮件，任务终止"
        )
        task.save(update_fields=["status", "error_message"])
        logger.warning(
            "任务 %d：轮询超时（%s）未收到报告邮件，标记为失败，不再续期",
            task_id,
            REPORT_EMAIL_POLL_TIMEOUT,
        )
    else:
        # 未收到，60 秒后重试
        logger.info("任务 %d：未收到报告邮件，60秒后重试", task_id)

        ScheduleQueryService().create_once_schedule(
            func="apps.automation.tasks.gsxt_tasks.check_gsxt_report_email",
            args=f"{task_id},{company_name!r}",
            name=f"gsxt_email_retry_{task_id}_{timezone.now().timestamp():.0f}",
            next_run=timezone.now() + timedelta(seconds=60),
        )
