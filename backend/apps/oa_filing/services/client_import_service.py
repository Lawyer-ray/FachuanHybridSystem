"""客户导入服务。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from apps.client.models import Client
from apps.oa_filing.models import ClientImportPhase, ClientImportSession, ClientImportStatus
from apps.oa_filing.services.oa_scripts.jtn_client_import import OACustomerData

if TYPE_CHECKING:
    from apps.organization.models import AccountCredential

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

    def run_import(self, *, headless: bool = True, limit: int | None = None) -> None:
        """执行导入流程。"""
        import django
        from apps.oa_filing.services.oa_scripts.jtn_client_import import JtnClientImportScript

        logger.info("开始导入客户，session_id=%d headless=%s limit=%s", self._session.id, headless, limit)

        # 先关闭所有数据库连接，因为 Playwright 会创建 asyncio 事件循环
        django.db.connections.close_all()

        try:
            started_at = self._session.started_at or timezone.now()
            self._update_session(
                status=ClientImportStatus.IN_PROGRESS,
                phase=ClientImportPhase.DISCOVERING,
                started_at=started_at,
                discovered_count=0,
                total_count=0,
                success_count=0,
                skip_count=0,
                error_message="",
                progress_message="正在登录OA并查找当事人列表",
            )

            script = JtnClientImportScript(
                account=self.credential.account,
                password=self.credential.password,
                headless=headless,
                progress_callback=self._handle_script_progress,
            )

            # 先收集所有数据
            all_customers: list[OACustomerData] = []
            for customer_data in script.run(limit=limit):
                all_customers.append(customer_data)

            logger.info("共收集到 %d 个客户", len(all_customers))

            # 现在重新连接数据库并保存
            django.db.connections.close_all()  # 确保新连接

            total_count = len(all_customers)
            success_count = 0
            skip_count = 0

            if total_count == 0:
                self._update_session(
                    status=ClientImportStatus.COMPLETED,
                    phase=ClientImportPhase.COMPLETED,
                    completed_at=timezone.now(),
                    progress_message="未发现可导入的当事人",
                )
                return

            for index, customer_data in enumerate(all_customers, start=1):
                result = self._import_single_client(customer_data)

                if result.status == "created":
                    success_count += 1
                elif result.status == "skipped":
                    skip_count += 1

                processed_count = success_count + skip_count
                self._update_session(
                    phase=ClientImportPhase.IMPORTING,
                    discovered_count=total_count,
                    total_count=total_count,
                    success_count=success_count,
                    skip_count=skip_count,
                    progress_message=f"正在导入当事人 ({processed_count}/{total_count})",
                )
                if index % 10 == 0:
                    logger.info("已处理 %d 条，成功 %d，跳过 %d", processed_count, success_count, skip_count)

            # 更新最终状态
            self._update_session(
                success_count=success_count,
                skip_count=skip_count,
                status=ClientImportStatus.COMPLETED,
                phase=ClientImportPhase.COMPLETED,
                completed_at=timezone.now(),
                progress_message="导入完成",
            )

            logger.info(
                "客户导入完成，total=%d, success=%d, skipped=%d",
                total_count,
                success_count,
                skip_count,
            )

        except Exception as exc:
            logger.exception("客户导入失败: %s", exc)
            self._update_session(
                status=ClientImportStatus.FAILED,
                phase=ClientImportPhase.FAILED,
                error_message=str(exc),
                completed_at=timezone.now(),
                progress_message="导入失败",
            )

    def _handle_script_progress(self, payload: dict[str, Any]) -> None:
        event = str(payload.get("event") or "")
        message = str(payload.get("message") or "").strip()

        if event == "discovery_started":
            self._update_session(
                phase=ClientImportPhase.DISCOVERING,
                progress_message=message or "正在查找并发现当事人",
            )
            return

        if event == "discovery_progress":
            discovered_count = self._to_int(payload.get("discovered_count"))
            page = self._to_int(payload.get("page"))
            if not message:
                message = f"正在查找并发现当事人（第{page}页）"
            self._update_session(
                phase=ClientImportPhase.DISCOVERING,
                discovered_count=discovered_count,
                progress_message=f"{message}，已发现 {discovered_count} 条",
            )
            return

        if event == "discovery_completed":
            total_count = self._to_int(payload.get("total_count") or payload.get("discovered_count"))
            self._update_session(
                phase=ClientImportPhase.DISCOVERING,
                discovered_count=total_count,
                total_count=total_count,
                progress_message=message or f"查找完成，共发现 {total_count} 条，准备导入",
            )
            return

        if event == "import_started":
            total_count = self._to_int(payload.get("total_count") or payload.get("discovered_count"))
            self._update_session(
                phase=ClientImportPhase.IMPORTING,
                discovered_count=total_count,
                total_count=total_count,
                progress_message=message or f"开始导入，共 {total_count} 条",
            )
            return

        if event in {"import_progress", "import_collected"}:
            total_count = self._to_int(payload.get("total_count")) or self._session.total_count
            discovered_count = self._to_int(payload.get("discovered_count")) or self._session.discovered_count
            index = self._to_int(payload.get("index"))
            current_name = str(payload.get("name") or "").strip()
            if not message and total_count > 0 and index > 0:
                message = f"正在导入当事人 ({index}/{total_count})"
            if current_name:
                message = f"{message}：{current_name}" if message else current_name
            self._update_session(
                phase=ClientImportPhase.IMPORTING,
                discovered_count=discovered_count,
                total_count=total_count,
                progress_message=message or "正在导入当事人",
            )

    def _update_session(self, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = timezone.now()
        ClientImportSession.objects.filter(pk=self._session.pk).update(**fields)
        for key, value in fields.items():
            if key != "updated_at":
                setattr(self._session, key, value)

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

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
