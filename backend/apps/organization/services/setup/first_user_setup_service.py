"""首位用户注册后的系统自动初始化服务

在首位用户（管理员）注册时自动完成系统基础设施初始化：
- 创建默认律所和团队
- 初始化 SystemConfig 配置条目
- 后台创建文书模板目录和默认文件夹模板
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction

if TYPE_CHECKING:
    from apps.organization.models import Lawyer

logger = logging.getLogger(__name__)


class FirstUserSetupService:
    """首位用户注册后的系统自动初始化服务"""

    def execute(self, admin_user: Lawyer) -> None:
        """执行全部初始化。

        同步部分在调用方的事务内执行；
        异步部分通过 daemon 线程在后台完成。
        """
        self._create_default_law_firm(admin_user)
        self._init_system_config()
        self._run_deferred_init()

    # ------------------------------------------------------------------
    # 同步初始化
    # ------------------------------------------------------------------

    def _create_default_law_firm(self, admin_user: Lawyer) -> None:
        """创建默认律所 + 律师团队 + 业务团队，并关联管理员用户。"""
        from apps.organization.models import LawFirm, Team, TeamType

        if admin_user.law_firm_id:
            logger.info("管理员已关联律所，跳过律所创建")
            return

        firm_name = f"{admin_user.real_name or admin_user.username}律师事务所"
        firm = LawFirm.objects.create(name=firm_name)
        Team.objects.create(name="默认律师团队", team_type=TeamType.LAWYER, law_firm=firm)
        Team.objects.create(name="默认业务团队", team_type=TeamType.BIZ, law_firm=firm)

        admin_user.law_firm = firm
        admin_user.save(update_fields=["law_firm"])

        logger.info("已创建默认律所「%s」及团队", firm_name)

    def _init_system_config(self) -> None:
        """初始化 SystemConfig 配置条目（幂等，仅创建不存在的条目）。"""
        from apps.core.admin._system_config_data import get_default_configs
        from apps.core.models import SystemConfig

        created_count = 0
        for config in get_default_configs():
            _, created = SystemConfig.objects.get_or_create(
                key=config["key"],
                defaults={
                    "value": config.get("value", ""),
                    "category": config["category"],
                    "description": config.get("description", ""),
                    "is_secret": config.get("is_secret", False),
                },
            )
            if created:
                created_count += 1

        logger.info("SystemConfig 初始化完成，新建 %d 条配置", created_count)

    # ------------------------------------------------------------------
    # 异步初始化（后台 daemon 线程）
    # ------------------------------------------------------------------

    def _run_deferred_init(self) -> None:
        """启动后台线程执行非关键初始化任务。"""
        thread = threading.Thread(target=self._deferred_worker, daemon=True, name="first-user-setup")
        thread.start()

    @staticmethod
    def _deferred_worker() -> None:
        """后台线程：创建文书模板目录和默认模板（文件夹+文书+绑定+代理事项规则）。"""
        try:
            FirstUserSetupService._init_document_directories()
        except Exception:
            logger.exception("文书模板目录创建失败")

        try:
            FirstUserSetupService._init_document_templates()
        except Exception:
            logger.exception("默认模板初始化失败")

        try:
            FirstUserSetupService._init_proxy_matter_rules()
        except Exception:
            logger.exception("代理事项规则初始化失败")

    @staticmethod
    def _init_document_directories() -> None:
        """创建文书模板存储目录（对应 init_document_system）。"""
        from apps.core.utils.path import Path

        media_root = Path(settings.MEDIA_ROOT)
        directories = [
            media_root / "document_templates",
            media_root / "document_templates" / "versions",
            media_root / "generated_documents",
        ]
        for directory in directories:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                logger.info("已创建目录: %s", directory)

    @staticmethod
    def _init_document_templates() -> None:
        """初始化默认文件夹模板 + 文书模板 + 绑定关系。"""
        from apps.documents.services.document_template.init_service import DocumentTemplateInitService

        service = DocumentTemplateInitService()
        result = service.initialize_default_templates()
        if result.get("success"):
            logger.info(
                "默认模板初始化完成：文件夹 %d(+%d跳过)，文书 %d(+%d跳过)，绑定 %d(+%d跳过)",
                result.get("folder_created", 0),
                result.get("folder_skipped", 0),
                result.get("doc_created", 0),
                result.get("doc_skipped", 0),
                result.get("binding_created", 0),
                result.get("binding_skipped", 0),
            )
        else:
            logger.warning("默认模板初始化失败: %s", result.get("error", result))

    @staticmethod
    def _init_proxy_matter_rules() -> None:
        """初始化代理事项规则默认数据。"""
        from apps.documents.services.proxy_matter_rule_init_service import ProxyMatterRuleInitService

        service = ProxyMatterRuleInitService()
        result = service.initialize_defaults()
        logger.info("代理事项规则初始化完成：创建 %d，更新 %d", result.get("created", 0), result.get("updated", 0))
