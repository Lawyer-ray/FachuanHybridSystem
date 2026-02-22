"""
案由法院数据初始化服务

负责从法院系统 API 获取案由和法院数据,并导入到数据库中.
支持增量更新、废弃标记和统计报告.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import TokenError
from apps.core.models import CauseOfAction, Court
from apps.core.repositories import CauseCourtRepository

from .court_api_client import CauseItem, CourtApiClient, CourtItem

if TYPE_CHECKING:
    from apps.core.interfaces import IAutoTokenAcquisitionService

logger = logging.getLogger(__name__)


@dataclass
class InitializationResult:
    """初始化结果

    Attributes:
        created: 新创建的记录数
        updated: 更新的记录数
        deprecated: 标记为废弃的记录数
        deleted: 物理删除的记录数
        failed: 失败的记录数
        errors: 错误信息列表
        warnings: 警告信息列表
    """

    created: int = 0
    updated: int = 0
    deprecated: int = 0
    deleted: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __add__(self, other: "InitializationResult") -> "InitializationResult":
        """合并两个初始化结果"""
        return InitializationResult(
            created=self.created + other.created,
            updated=self.updated + other.updated,
            deprecated=self.deprecated + other.deprecated,
            deleted=self.deleted + other.deleted,
            failed=self.failed + other.failed,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )

    @property
    def total_processed(self) -> int:
        """总处理数量"""
        return self.created + self.updated + self.deprecated + self.deleted

    @property
    def success(self) -> bool:
        """是否成功(无失败记录)"""
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "created": self.created,
            "updated": self.updated,
            "deprecated": self.deprecated,
            "deleted": self.deleted,
            "failed": self.failed,
            "total_processed": self.total_processed,
            "success": self.success,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class CauseCourtInitializationService:
    """案由法院数据初始化服务

    负责从法院系统 API 获取案由和法院数据,并导入到数据库中.

    Features:
        - 支持通过 credential_id 获取 Token
        - 支持自动登录获取 Token(无可用 Token 时)
        - 支持增量更新(新增、更新、废弃)
        - 支持层级结构解析
        - 提供详细的统计报告
    """

    # 法院系统站点名称(用于登录和案由 API)
    COURT_SITE_NAME = "court_zxfw"
    BAOQUAN_SITE_NAME = "court_baoquan"
    _BAOQUAN_TOKEN_PREFIX = "eyJhbGciOiJIUzUxMiJ9"

    def __init__(
        self,
        api_client: CourtApiClient | None = None,
        auto_token_service: "IAutoTokenAcquisitionService | None" = None,
        repository: CauseCourtRepository | None = None,
    ) -> None:
        """初始化服务

        Args:
            api_client: 法院 API 客户端,为 None 时创建新实例
            auto_token_service: 自动 Token 获取服务,为 None 时使用 ServiceLocator 获取
            repository: 数据访问层,为 None 时创建新实例
        """
        self._api_client = api_client
        self._auto_token_service = auto_token_service
        self._repository = repository or CauseCourtRepository()

    @property
    def api_client(self) -> CourtApiClient:
        """延迟加载 API 客户端"""
        if self._api_client is None:
            self._api_client = CourtApiClient()
        return self._api_client

    @property
    def auto_token_service(self) -> "IAutoTokenAcquisitionService":
        """延迟加载自动 Token 获取服务"""
        if self._auto_token_service is None:
            from .wiring import get_auto_token_acquisition_service

            self._auto_token_service = get_auto_token_acquisition_service()
        return self._auto_token_service

    async def initialize_causes(
        self,
        credential_id: int | None = None,
    ) -> InitializationResult:
        """初始化案由数据

        从法院一张网 API 获取所有案由数据(刑事、民事、行政),并导入到数据库中.
        支持增量更新:新增、更新、废弃.

        Args:
            credential_id: 凭证 ID,可选.如果不指定则使用任意可用的 Token

        Returns:
            InitializationResult 初始化结果

        Raises:
            NotFoundError: 找不到可用的凭证或 Token
            ValidationException: API 请求或数据解析失败
        """
        logger.info("开始初始化案由数据...")

        # 1. 获取一张网 Token(HS256 格式)
        token = await self._get_zxfw_token(credential_id)

        # 2. 获取所有案由(刑事、民事、行政)
        all_cause_items = await self.api_client.fetch_all_causes(token)

        if not all_cause_items:
            logger.warning("API 返回的案由数据为空")
            return InitializationResult(warnings=["API 返回的案由数据为空"])

        # 3. 收集所有案由编码(用于检测废弃的案由)
        api_codes = self._collect_cause_codes(all_cause_items)
        logger.info(f"API 返回 {len(api_codes)} 个案由编码")

        # 4. 导入数据到数据库
        result = await sync_to_async(self._import_causes_to_db)(all_cause_items)

        # 5. 处理废弃的案由
        deprecate_result = await sync_to_async(self._deprecate_removed_causes)(api_codes)
        result = result + deprecate_result

        logger.info(
            f"案由数据初始化完成: 新增 {result.created}, 更新 {result.updated}, "
            f"废弃 {result.deprecated}, 删除 {result.deleted}, 失败 {result.failed}"
        )

        return result

    async def _get_zxfw_token(self, credential_id: int | None = None) -> str:
        """获取法院一张网 Token (HS256 格式)

        Args:
            credential_id: 凭证 ID,可选

        Returns:
            一张网 Token 字符串 (HS256 格式)

        Raises:
            TokenError: Token 获取失败
        """
        logger.info("获取一张网 Token (HS256)...")

        # 1. 检查现有一张网 Token
        from .wiring import get_court_token_store_service

        token_store = get_court_token_store_service()
        token_info = await sync_to_async(token_store.get_latest_valid_token_internal)(
            site_name=self.COURT_SITE_NAME,
            token_prefix="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",
        )
        if token_info:
            logger.info(f"✅ 找到现有有效一张网 Token: {token_info.account}")
            return token_info.token

        # 2. 如果没有有效 Token,需要登录获取
        logger.info("无现有有效一张网 Token,将自动获取")
        token = await self._acquire_zxfw_token(credential_id)

        return token

    async def _acquire_zxfw_token(self, credential_id: int | None = None) -> str:
        """自动登录并获取一张网 Token

        Args:
            credential_id: 凭证 ID,可选

        Returns:
            一张网 Token 字符串

        Raises:
            TokenError: 获取失败
        """
        from .wiring import get_court_token_store_service, get_organization_service

        organization_service = get_organization_service()
        token_store = get_court_token_store_service()

        if credential_id:
            credential = await sync_to_async(organization_service.get_credential_internal)(credential_id)
        else:
            all_credentials = await sync_to_async(organization_service.get_all_credentials_internal)()
            credentials = [c for c in all_credentials if "zxfw.court.gov.cn" in (c.url or "")]
            if not credentials:
                raise TokenError("没有找到法院一张网的账号凭证")
            credential = credentials[0]

        account = credential.account
        password = credential.password

        logger.info(f"使用账号 {account} 登录获取一张网 Token")

        def _do_login() -> str | None:
            """同步执行登录"""
            from playwright.sync_api import sync_playwright

            from apps.core.services.wiring import get_anti_detection, get_court_zxfw_service_factory

            anti_detection = get_anti_detection()

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context_options = anti_detection.get_browser_context_options()
                context = browser.new_context(**context_options)
                page = context.new_page()

                try:
                    service = get_court_zxfw_service_factory(page=page, context=context)

                    # 登录
                    login_result = service.login(
                        account=account,
                        password=password,
                        max_captcha_retries=3,
                        save_debug=False,
                    )

                    if not login_result.get("success"):
                        raise TokenError(f"登录失败: {login_result.get('message')}")

                    # 获取一张网 Token
                    token_val = login_result.get("token")
                    return str(token_val) if token_val is not None else None

                finally:
                    context.close()
                    browser.close()

        import asyncio

        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, _do_login)

        if not token:
            raise TokenError("登录成功但未获取到 Token")

        # 保存 Token
        await sync_to_async(token_store.save_token_internal)(
            site_name=self.COURT_SITE_NAME,
            account=account,
            token=token,
            expires_in=3600,  # 一张网 Token 有效期 1 小时
        )

        logger.info(f"✅ 一张网 Token 已保存: {account}")
        return token

    async def _get_token(self, credential_id: int | None = None) -> str:
        from .wiring import get_baoquan_token_service

        baoquan_token_service = get_baoquan_token_service()
        return await baoquan_token_service.get_valid_baoquan_token(credential_id)

    def _collect_cause_codes(self, items: list[CauseItem]) -> set[str]:
        """递归收集所有案由编码

        Args:
            items: 案由数据项列表

        Returns:
            所有案由编码的集合
        """
        codes: set[str] = set()
        for item in items:
            codes.add(item.code)
            if item.children:
                codes.update(self._collect_cause_codes(item.children))
        return codes

    @transaction.atomic
    def _import_causes_to_db(self, items: list[CauseItem]) -> InitializationResult:
        """导入案由数据到数据库

        Args:
            items: 案由数据项列表

        Returns:
            InitializationResult 初始化结果
        """
        result = InitializationResult()

        for item in items:
            item_result = self._parse_hierarchical_causes(
                item=item,
                parent=None,
            )
            result = result + item_result

        return result

    def _parse_hierarchical_causes(
        self,
        item: CauseItem,
        parent: CauseOfAction | None = None,
    ) -> InitializationResult:
        """递归解析层级案由数据

        处理单个案由项及其子项,支持新增和更新.

        Args:
            item: 案由数据项
            parent: 父级案由实例

        Returns:
            InitializationResult 初始化结果
        """
        result = InitializationResult()

        try:
            # 查找或创建案由记录
            cause, created = self._repository.update_or_create_cause(
                code=item.code,
                defaults={
                    "name": item.name,
                    "case_type": item.case_type,
                    "parent": parent,
                    "level": item.level,
                    "is_active": True,
                    "is_deprecated": False,
                    "deprecated_at": None,
                    "deprecated_reason": "",
                },
            )

            if created:
                result.created += 1
                logger.debug(f"创建案由: {item.code} - {item.name}")
            else:
                result.updated += 1
                logger.debug(f"更新案由: {item.code} - {item.name}")

            # 递归处理子级
            for child_item in item.children:
                child_result = self._parse_hierarchical_causes(
                    item=child_item,
                    parent=cause,
                )
                result = result + child_result

        except Exception as e:
            result.failed += 1
            error_msg = f"处理案由 {item.code} 失败: {e}"
            result.errors.append(error_msg)
            logger.error(error_msg)

        return result

    @transaction.atomic
    def _deprecate_removed_causes(self, api_codes: set[str]) -> InitializationResult:
        """处理 API 中已移除的案由

        对于数据库中存在但 API 中不存在的案由:
        - 如果有关联的诉讼模板,标记为废弃
        - 如果没有关联,物理删除

        Args:
            api_codes: API 返回的所有案由编码集合

        Returns:
            InitializationResult 初始化结果
        """
        result = InitializationResult()

        # 查找数据库中存在但 API 中不存在的案由
        db_causes = self._repository.get_non_deprecated_causes_excluding_codes(list(api_codes))

        for cause in db_causes:
            try:
                # 检查是否有关联的诉讼模板
                has_templates = self._cause_has_templates(cause)

                if has_templates:
                    # 有关联模板,标记为废弃
                    cause.is_deprecated = True
                    cause.deprecated_at = timezone.now()
                    cause.deprecated_reason = "法院系统已移除此案由"
                    cause.save()
                    result.deprecated += 1
                    result.warnings.append(f"案由 {cause.code} ({cause.name}) 已废弃,但保留因有关联模板")
                    logger.info(f"标记案由为废弃: {cause.code} - {cause.name}")
                else:
                    # 无关联模板,物理删除
                    cause.delete()
                    result.deleted += 1
                    logger.info(f"删除案由: {cause.code} - {cause.name}")

            except Exception as e:
                result.failed += 1
                error_msg = f"处理废弃案由 {cause.code} 失败: {e}"
                result.errors.append(error_msg)
                logger.error(error_msg)

        return result

    def _cause_has_templates(self, cause: CauseOfAction) -> bool:
        """检查案由是否有关联的诉讼模板(已废弃)

        Args:
            cause: 案由实例

        Returns:
            始终返回 False(诉状模板功能已移除)
        """
        # 诉状模板功能已移除,始终返回 False
        return False

    async def initialize_courts(
        self,
        credential_id: int | None = None,
    ) -> InitializationResult:
        """初始化法院数据

        从法院系统 API 获取法院数据,并导入到数据库中.
        支持增量更新:新增、更新、删除.

        Args:
            credential_id: 凭证 ID,可选.如果不指定则使用任意可用的 Token

        Returns:
            InitializationResult 初始化结果

        Raises:
            NotFoundError: 找不到可用的凭证或 Token
            ValidationException: API 请求或数据解析失败
        """
        logger.info("开始初始化法院数据...")

        # 1. 获取 Token
        token = await self._get_token(credential_id)

        # 2. 从 API 获取数据
        response_data = await self.api_client.fetch_courts(token)

        # 3. 解析响应数据
        court_items = self.api_client.parse_court_response(response_data)
        if not court_items:
            logger.warning("API 返回的法院数据为空")
            return InitializationResult(warnings=["API 返回的法院数据为空"])

        # 4. 收集所有法院编码(用于检测删除的法院)
        api_codes = self._collect_court_codes(court_items)
        logger.info(f"API 返回 {len(api_codes)} 个法院编码")

        # 5. 导入数据到数据库
        result = await sync_to_async(self._import_courts_to_db)(court_items)

        # 6. 处理删除的法院
        delete_result = await sync_to_async(self._delete_removed_courts)(api_codes)
        result = result + delete_result

        logger.info(
            f"法院数据初始化完成: 新增 {result.created}, 更新 {result.updated}, "
            f"删除 {result.deleted}, 失败 {result.failed}"
        )

        return result

    def _collect_court_codes(self, items: list[CourtItem]) -> set[str]:
        """递归收集所有法院编码

        Args:
            items: 法院数据项列表

        Returns:
            所有法院编码的集合
        """
        codes: set[str] = set()
        for item in items:
            codes.add(item.code)
            if item.children:
                codes.update(self._collect_court_codes(item.children))
        return codes

    @transaction.atomic
    def _import_courts_to_db(self, items: list[CourtItem]) -> InitializationResult:
        """导入法院数据到数据库

        Args:
            items: 法院数据项列表

        Returns:
            InitializationResult 初始化结果
        """
        result = InitializationResult()

        for item in items:
            item_result = self._parse_hierarchical_courts(
                item=item,
                parent=None,
            )
            result = result + item_result

        return result

    def _parse_hierarchical_courts(
        self,
        item: CourtItem,
        parent: Court | None = None,
    ) -> InitializationResult:
        """递归解析层级法院数据

        处理单个法院项及其子项,支持新增和更新.

        Args:
            item: 法院数据项
            parent: 父级法院实例

        Returns:
            InitializationResult 初始化结果
        """
        result = InitializationResult()

        try:
            # 查找或创建法院记录
            court, created = self._repository.update_or_create_court(
                code=item.code,
                defaults={
                    "name": item.name,
                    "parent": parent,
                    "level": item.level,
                    "province": item.province,
                    "is_active": True,
                },
            )

            if created:
                result.created += 1
                logger.debug(f"创建法院: {item.code} - {item.name}")
            else:
                result.updated += 1
                logger.debug(f"更新法院: {item.code} - {item.name}")

            # 递归处理子级
            for child_item in item.children:
                child_result = self._parse_hierarchical_courts(
                    item=child_item,
                    parent=court,
                )
                result = result + child_result

        except Exception as e:
            result.failed += 1
            error_msg = f"处理法院 {item.code} 失败: {e}"
            result.errors.append(error_msg)
            logger.error(error_msg)

        return result

    @transaction.atomic
    def _delete_removed_courts(self, api_codes: set[str]) -> InitializationResult:
        """删除 API 中已移除的法院

        对于数据库中存在但 API 中不存在的法院,直接物理删除.

        Args:
            api_codes: API 返回的所有法院编码集合

        Returns:
            InitializationResult 初始化结果
        """
        result = InitializationResult()

        # 查找数据库中存在但 API 中不存在的法院
        db_courts = self._repository.get_courts_excluding_codes(list(api_codes))

        for court in db_courts:
            try:
                court.delete()
                result.deleted += 1
                logger.info(f"删除法院: {court.code} - {court.name}")
            except Exception as e:
                result.failed += 1
                error_msg = f"删除法院 {court.code} 失败: {e}"
                result.errors.append(error_msg)
                logger.error(error_msg)

        return result
