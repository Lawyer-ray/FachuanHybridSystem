"""客户导入服务。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from django.db import transaction

from apps.client.models import Client
from apps.oa_filing.models import ClientImportSession
from apps.oa_filing.services.oa_scripts.jtn_client_import import OACustomerData

if TYPE_CHECKING:
    from apps.organization.models import AccountCredential, Lawyer

logger = logging.getLogger("apps.oa_filing.client_import_service")


@dataclass
class ImportResult:
    """导入结果。"""

    status: str  # created / skipped / error
    message: str


class ClientImportService:
    """客户导入服务。"""

    def __init__(self, session: ClientImportSession) -> None:
        self._session = session
        self._credential: AccountCredential | None = None

    @property
    def credential(self) -> AccountCredential:
        """获取OA凭证。"""
        if self._credential is None:
            assert self._session.credential is not None
            self._credential = self._session.credential
        return self._credential

    def run_import(self) -> None:
        """执行导入流程。"""
        import django
        from apps.oa_filing.services.oa_scripts.jtn_client_import import JtnClientImportScript

        logger.info("开始导入客户，session_id=%d", self._session.id)

        # 先关闭所有数据库连接，因为 Playwright 会创建 asyncio 事件循环
        django.db.connections.close_all()

        try:
            script = JtnClientImportScript(
                account=self.credential.account,
                password=self.credential.password,
            )

            # 先收集所有数据
            all_customers = []
            for customer_data in script.run():
                all_customers.append(customer_data)

            logger.info("共收集到 %d 个客户", len(all_customers))

            # 现在重新连接数据库并保存
            django.db.connections.close_all()  # 确保新连接

            # 更新状态为进行中
            self._session.status = "in_progress"
            self._session.started_at = datetime.now()
            self._session.total_count = len(all_customers)
            self._session.save()

            total_count = len(all_customers)
            success_count = 0
            skip_count = 0

            for customer_data in all_customers:
                result = self._import_single_client(customer_data)

                if result.status == "created":
                    success_count += 1
                elif result.status == "skipped":
                    skip_count += 1

                # 每10条更新一次状态
                if (success_count + skip_count) % 10 == 0:
                    self._session.success_count = success_count
                    self._session.skip_count = skip_count
                    self._session.save()
                    logger.info("已处理 %d 条，成功 %d，跳过 %d", success_count + skip_count, success_count, skip_count)

            # 更新最终状态
            self._session.success_count = success_count
            self._session.skip_count = skip_count
            self._session.status = "completed"
            self._session.completed_at = datetime.now()
            self._session.save()

            logger.info(
                "客户导入完成，total=%d, success=%d, skipped=%d",
                total_count,
                success_count,
                skip_count,
            )

        except Exception as exc:
            logger.exception("客户导入失败: %s", exc)
            self._session.status = "failed"
            self._session.error_message = str(exc)
            self._session.completed_at = datetime.now()
            self._session.save()

    def _import_single_client(self, data: OACustomerData) -> ImportResult:
        """导入单条客户数据。"""
        try:
            # 按名称去重
            exists = Client.objects.filter(name=data.name).exists()
            if exists:
                logger.info("客户已存在，跳过: %s", data.name)
                return ImportResult(status="skipped", message="客户已存在")

            # 创建客户
            with transaction.atomic():
                client = Client.objects.create(
                    name=data.name,
                    client_type="legal" if data.client_type == "legal" else "natural",
                    phone=data.phone or "",
                    address=data.address or "",
                    id_number=data.id_number or "",
                    legal_representative=data.legal_representative or "",
                    is_our_client=True,  # OA客户都是我方当事人
                )

            logger.info("创建客户成功: %s (id=%d)", data.name, client.id)
            return ImportResult(status="created", message=f"创建成功 (id={client.id})")

        except Exception as exc:
            logger.warning("导入客户异常 %s: %s", data.name, exc)
            return ImportResult(status="error", message=str(exc))