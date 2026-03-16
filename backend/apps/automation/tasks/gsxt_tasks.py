"""国家企业信用信息公示系统相关 Django-Q 任务函数。"""

from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path

from django.apps import apps as django_apps

logger = logging.getLogger("apps.automation")


def check_gsxt_report_email(task_id: int, company_name: str) -> None:
    """
    Django-Q 任务：检查邮箱是否收到企业信用报告，收到则保存为营业执照附件。
    未收到时重新入队（60秒后再试），直到任务状态不再是 WAITING_EMAIL 为止。
    """
    from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask
    from apps.automation.services.gsxt.gsxt_email_service import (
        EMAIL_CREDENTIAL_ID,
        _fetch_report_attachment,
    )
    from django.conf import settings
    from django_q.tasks import async_task

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
        abs_path = Path(settings.MEDIA_ROOT) / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(pdf_bytes)

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
    else:
        # 未收到，60 秒后重试
        logger.info("任务 %d：未收到报告邮件，60秒后重试", task_id)
        from datetime import timedelta

        from django.utils import timezone
        from django_q.models import Schedule

        Schedule.objects.create(
            func="apps.automation.tasks.gsxt_tasks.check_gsxt_report_email",
            args=f"{task_id},{company_name!r}",
            schedule_type=Schedule.ONCE,
            next_run=timezone.now() + timedelta(seconds=60),
            name=f"gsxt_email_retry_{task_id}_{timezone.now().timestamp():.0f}",
        )
