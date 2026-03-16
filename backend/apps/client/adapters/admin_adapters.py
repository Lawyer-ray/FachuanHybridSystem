"""Admin 层适配器实现。

实现对 Admin 端口的具体适配，封装对外部模块的调用。
"""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Any

from django.apps import apps as django_apps
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


def _get_gsxt_report_task_model() -> Any:
    return django_apps.get_model("automation", "GsxtReportTask")


def _get_gsxt_report_status_enum() -> Any:
    module = import_module("apps.automation.models.gsxt_report")
    return module.GsxtReportStatus


def _get_account_credential_model() -> Any:
    return django_apps.get_model("organization", "AccountCredential")


class GsxtReportAdapter:
    """企业信用报告适配器。"""

    def create_report_task(
        self,
        client_id: int,
        company_name: str,
        credit_code: str,
    ) -> int:
        """创建报告下载任务。"""
        gsxt_report_task_model = _get_gsxt_report_task_model()
        gsxt_report_status = _get_gsxt_report_status_enum()

        task = gsxt_report_task_model.objects.create(
            client_id=client_id,
            company_name=company_name,
            credit_code=credit_code,
            status=gsxt_report_status.WAITING_CAPTCHA,
        )
        logger.info(f"创建企业信用报告任务: client_id={client_id}, task_id={task.id}")
        return task.id

    def start_login(self, credential_id: int, task_id: int) -> None:
        """启动登录流程。"""
        from apps.automation.services.gsxt.gsxt_login_service import (
            start_login_gsxt,
        )

        account_credential_model = _get_account_credential_model()
        credential = account_credential_model.objects.get(pk=credential_id)
        start_login_gsxt(credential, task_id)
        logger.info(f"启动国家企业信用信息公示系统登录: task_id={task_id}")

    def get_waiting_email_task(self, client_id: int) -> Any | None:
        """获取等待邮件的任务。"""
        gsxt_report_task_model = _get_gsxt_report_task_model()
        gsxt_report_status = _get_gsxt_report_status_enum()

        return gsxt_report_task_model.objects.filter(
            client_id=client_id,
            status=gsxt_report_status.WAITING_EMAIL,
        ).first()

    def upload_report(self, task_id: int, file_content: bytes, file_name: str) -> bool:
        """上传报告文件。"""
        gsxt_report_task_model = _get_gsxt_report_task_model()
        gsxt_report_status = _get_gsxt_report_status_enum()

        try:
            task = gsxt_report_task_model.objects.get(id=task_id)
            task.report_file.save(file_name, ContentFile(file_content), save=True)
            task.status = gsxt_report_status.SUCCESS
            task.save(update_fields=["report_file", "status", "updated_at"])
            logger.info(f"上传企业信用报告成功: task_id={task_id}")
            return True
        except Exception as e:
            logger.error(f"上传企业信用报告失败: task_id={task_id}, error={e}")
            return False

    def get_task_status_choices(self) -> list[tuple[str, str]]:
        """获取任务状态选项。"""
        gsxt_report_status = _get_gsxt_report_status_enum()

        return gsxt_report_status.choices


class CredentialAdapter:
    """账号凭证适配器。"""

    def get_gsxt_credential(self) -> Any | None:
        """获取国家企业信用信息公示系统的登录凭证。

        返回成功率最高且最近成功登录的凭证。
        """
        account_credential_model = _get_account_credential_model()
        return (
            account_credential_model.objects.filter(site_name__icontains="国家企业信用")
            .order_by("-last_login_success_at", "-login_success_count")
            .first()
        )
