"""Admin 层端口定义。

定义 Admin 层需要的外部服务接口，用于解耦对其他模块的依赖。
"""

from __future__ import annotations

from typing import Any, Protocol


class GsxtReportPort(Protocol):
    """企业信用报告服务端口。

    封装对 automation 模块的依赖，提供企业信用报告相关操作。
    """

    def create_report_task(
        self,
        client_id: int,
        company_name: str,
        credit_code: str,
    ) -> int:
        """创建报告下载任务。

        Args:
            client_id: 当事人ID
            company_name: 企业名称
            credit_code: 统一社会信用代码

        Returns:
            任务ID
        """
        ...

    def start_login(self, credential_id: int, task_id: int) -> None:
        """启动登录流程。

        Args:
            credential_id: 凭证ID
            task_id: 任务ID
        """
        ...

    def get_waiting_email_task(self, client_id: int) -> Any | None:
        """获取等待邮件的任务。

        Args:
            client_id: 当事人ID

        Returns:
            任务对象或 None
        """
        ...

    def upload_report(self, task_id: int, file_content: bytes, file_name: str) -> bool:
        """上传报告文件。

        Args:
            task_id: 任务ID
            file_content: 文件内容
            file_name: 文件名

        Returns:
            是否成功
        """
        ...

    def get_task_status_choices(self) -> list[tuple[str, str]]:
        """获取任务状态选项（用于 Admin 下拉框）。

        Returns:
            状态选项列表
        """
        ...


class CredentialPort(Protocol):
    """账号凭证服务端口。

    封装对 organization 模块的依赖，提供账号凭证相关操作。
    """

    def get_gsxt_credential(self) -> Any | None:
        """获取国家企业信用信息公示系统的登录凭证。

        Returns:
            凭证对象或 None
        """
        ...
