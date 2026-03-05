"""国家企业信用信息公示系统相关 Django-Q 任务函数。"""

from __future__ import annotations

import logging
from pathlib import Path

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
    from apps.client.models.identity_doc import ClientIdentityDoc
    from apps.organization.models.credential import AccountCredential
    from django.conf import settings
    from django_q.tasks import async_task

    task = GsxtReportTask.objects.select_related("client").get(pk=task_id)

    # 任务已终态，不再重试
    if task.status not in (GsxtReportStatus.WAITING_EMAIL,):
        return

    cred = AccountCredential.objects.get(pk=EMAIL_CREDENTIAL_ID)
    pdf_bytes = _fetch_report_attachment(cred.account, cred.password, company_name)

    if pdf_bytes:
        client = task.client
        rel_path = f"client_docs/{client.pk}/{company_name[:20]}_企业信用报告.pdf"
        abs_path = Path(settings.MEDIA_ROOT) / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(pdf_bytes)

        doc, _ = ClientIdentityDoc.objects.get_or_create(
            client=client,
            doc_type=ClientIdentityDoc.BUSINESS_LICENSE,
        )
        doc.file_path = str(rel_path)
        doc.save(update_fields=["file_path"])

        task.status = GsxtReportStatus.SUCCESS
        task.error_message = ""
        task.save(update_fields=["status", "error_message"])
        logger.info("任务 %d：报告已保存为营业执照附件，client_id=%d", task_id, client.pk)
    else:
        # 未收到，60 秒后重试
        logger.info("任务 %d：未收到报告邮件，60秒后重试", task_id)
        async_task(
            "apps.automation.tasks.gsxt_tasks.check_gsxt_report_email",
            task_id,
            company_name,
            q_options={"countdown": 60},
        )
