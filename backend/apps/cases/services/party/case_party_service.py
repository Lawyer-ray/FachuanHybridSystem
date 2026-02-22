"""Business logic services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from django.db import transaction
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.cases.models import CaseParty
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.core.business_config import business_config
from apps.core.exceptions import ValidationException
from apps.core.interfaces import ICaseService, IClientService, IContractService

if TYPE_CHECKING:
    from .case_party_mutation_facade import CasePartyMutationFacade
    from .case_party_query_facade import CasePartyQueryFacade

logger = logging.getLogger("apps.cases")


class CasePartyService:
    """
    案件当事人服务

    职责:
    1. 封装案件当事人相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 支持依赖注入
    """

    def __init__(
        self,
        case_service: ICaseService | None = None,
        client_service: IClientService | None = None,
        contract_service: IContractService | None = None,
    ) -> None:
        """
        初始化服务(依赖注入)

        Args:
            case_service: 案件服务接口(注入)
            client_service: 客户服务接口(注入)
            contract_service: 合同服务接口(注入)
        """
        self._case_service = case_service
        self._client_service = client_service
        self._contract_service = contract_service
        self._access_policy: CaseAccessPolicy | None = None
        self._query_facade: CasePartyQueryFacade | None = None
        self._mutation_facade: CasePartyMutationFacade | None = None

    @property
    def case_service(self) -> ICaseService:
        """延迟加载:优先使用注入实例"""
        if self._case_service is None:
            raise RuntimeError("CasePartyService.case_service 未注入")
        return self._case_service

    @property
    def client_service(self) -> IClientService:
        """延迟加载:优先使用注入实例"""
        if self._client_service is None:
            raise RuntimeError("CasePartyService.client_service 未注入")
        return self._client_service

    @property
    def contract_service(self) -> IContractService:
        """延迟加载:优先使用注入实例"""
        if self._contract_service is None:
            raise RuntimeError("CasePartyService.contract_service 未注入")
        return self._contract_service

    @property
    def access_policy(self) -> CaseAccessPolicy:
        if self._access_policy is None:
            self._access_policy = CaseAccessPolicy()
        return self._access_policy

    @property
    def query_facade(self) -> CasePartyQueryFacade:
        if self._query_facade is None:
            from .case_party_query_facade import CasePartyQueryFacade

            self._query_facade = CasePartyQueryFacade(access_policy=self.access_policy)
        return self._query_facade

    @property
    def mutation_facade(self) -> CasePartyMutationFacade:
        if self._mutation_facade is None:
            from .case_party_mutation_facade import CasePartyMutationFacade
            from .case_party_mutation_service import CasePartyMutationService
            from .case_party_query_service import CasePartyQueryService

            self._mutation_facade = CasePartyMutationFacade(
                mutation_service=CasePartyMutationService(
                    client_service=self.client_service,
                    contract_service=self.contract_service,
                ),
                query_service=CasePartyQueryService(),
                access_policy=self.access_policy,
            )
        return self._mutation_facade

    def _require_case_access(
        self,
        case_id: int,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> None:
        self.access_policy.ensure_access(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def validate_party_in_contract_scope(
        self,
        case_id: int,
        client_id: int,
    ) -> bool:
        """
        验证当事人是否在案件绑定合同的范围内

        当案件绑定了合同时,验证 client 是否属于该合同或其补充协议的当事人.
        当案件未绑定合同时,允许任意 client.

        Args:
            case_id: 案件 ID
            client_id: 客户 ID

        Returns:
            True 如果验证通过(无合同或在范围内)

        Raises:
            ValidationException: 当事人不在合同范围内
            NotFoundError: 案件不存在

        Requirements: 4.1, 4.2, 4.3
        """
        return self.mutation_facade.mutation_service.validate_party_in_contract_scope(case_id, client_id)

    def validate_legal_status_compatibility(
        self,
        case_id: int,
        legal_status: str,
        exclude_party_id: int | None = None,
        client_id: int | None = None,
    ) -> bool:
        """
        验证诉讼地位与案件中其他当事人的兼容性

        Args:
            case_id: 案件 ID
            legal_status: 要验证的诉讼地位
            exclude_party_id: 排除的当事人 ID(用于更新场景)
            client_id: 当事人关联的客户 ID(用于我方当事人验证)

        Returns:
            True 如果兼容

        Raises:
            ValidationException: 诉讼地位不兼容
            NotFoundError: 案件不存在

        Requirements: 7.1, 7.2, 7.3
        """
        return self.mutation_facade.mutation_service.validate_legal_status_compatibility(
            case_id=case_id,
            legal_status=legal_status,
            exclude_party_id=exclude_party_id,
            client_id=client_id,
        )

    def _validate_our_party_legal_status(
        self,
        case_id: int,
        legal_status: str,
        client_id: int,
        parties_qs: QuerySet[Any, Any],
    ) -> None:
        """
        验证我方当事人诉讼地位冲突

        我方当事人(is_our_client=True)在同一案件中不能同时处于对立阵营.

        Args:
            case_id: 案件 ID
            legal_status: 要验证的诉讼地位
            client_id: 当事人关联的客户 ID
            parties_qs: 已过滤的当事人查询集

        Raises:
            ValidationException: 我方当事人诉讼地位冲突
        """
        # 获取当前客户信息
        client_dto = self.client_service.get_client_internal(client_id)
        if not client_dto or not client_dto.is_our_client:
            # 非我方当事人,无需验证
            return

        # 获取新诉讼地位的阵营
        new_status_config = business_config.is_legal_status_valid_for_case_type(legal_status, None)
        if not new_status_config:
            return
        new_group = legal_status

        # 定义对立阵营映射
        opposing_groups = {
            "plaintiff_side": "defendant_side",
            "defendant_side": "plaintiff_side",
            "appellant_side": "appellee_side",
            "appellee_side": "appellant_side",
            "applicant_side": "respondent_side",
            "respondent_side": "applicant_side",
            "criminal_defendant_side": "criminal_victim_side",
            "criminal_victim_side": "criminal_defendant_side",
        }

        opposing_group = opposing_groups.get(new_group)
        if not opposing_group:
            # 无对立阵营(如第三人),无需验证
            return

        # 查询案件中其他我方当事人的诉讼地位
        our_party_statuses = list(
            parties_qs.filter(client__is_our_client=True)
            .exclude(legal_status__isnull=True)
            .exclude(legal_status="")
            .values_list("legal_status", "client__name")
        )

        # 检查是否有我方当事人处于对立阵营
        for existing_status, client_name in our_party_statuses:
            existing_in_opposing = (
                existing_status in opposing_groups
                and opposing_groups.get(existing_status) == new_group
            )
            if existing_in_opposing:
                new_status_label = business_config.get_legal_status_label(legal_status)
                existing_status_label = business_config.get_legal_status_label(existing_status)

                logger.warning(
                    "我方当事人诉讼地位冲突",
                    extra={
                        "action": "validate_our_party_legal_status",
                        "case_id": case_id,
                        "client_id": client_id,
                        "legal_status": legal_status,
                        "conflicting_status": existing_status,
                        "conflicting_client": client_name,
                    },
                )

                raise ValidationException(
                    message=_(
                        "我方当事人诉讼地位冲突:案件中已有我方当事人「%(name)s」"
                        "为%(existing)s,不能再添加我方当事人为%(new)s"
                    ) % {"name": client_name, "existing": existing_status_label, "new": new_status_label},
                    code="OUR_PARTY_LEGAL_STATUS_CONFLICT",
                    errors={
                        "legal_status": "我方当事人不能同时处于对立诉讼地位",
                        "conflicting_party": client_name,
                        "conflicting_status": existing_status,
                    },
                )

    def get_available_legal_statuses(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[dict[str, str]]:
        """
        获取案件可用的诉讼地位列表

        Args:
            case_id: 案件 ID

        Returns:
            [{"value": "plaintiff", "label": "原告"}, ...]

        Raises:
            NotFoundError: 案件不存在

        Requirements: 6.1, 6.2
        """
        return self.query_facade.get_available_legal_statuses(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def list_parties(
        self,
        case_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[CaseParty, CaseParty]:
        """
        获取当事人列表

        Args:
            case_id: 案件 ID(可选,用于过滤)
            user: 当前用户

        Returns:
            当事人查询集
        """
        return cast(
            QuerySet[CaseParty, CaseParty],
            self.query_facade.list_parties(
                case_id=case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    def get_party(
        self,
        party_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseParty:
        """
        获取单个当事人

        Args:
            party_id: 当事人 ID
            user: 当前用户

        Returns:
            当事人对象

        Raises:
            NotFoundError: 当事人不存在
        """
        return cast(
            CaseParty,
            self.query_facade.get_party(
                party_id=party_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def create_party(
        self,
        case_id: int,
        client_id: int,
        legal_status: str | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseParty:
        """
        创建当事人

        Args:
            case_id: 案件 ID
            client_id: 客户 ID
            legal_status: 诉讼地位(可选)
            user: 当前用户

        Returns:
            创建的当事人对象

        Raises:
            NotFoundError: 案件或客户不存在
            ConflictError: 当事人已存在
            ValidationException: 数据验证失败
        """
        return cast(
            CaseParty,
            self.mutation_facade.create_party(
                case_id=case_id,
                client_id=client_id,
                legal_status=legal_status,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def update_party(
        self,
        party_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseParty:
        """
        更新当事人

        Args:
            party_id: 当事人 ID
            data: 更新数据
            user: 当前用户

        Returns:
            更新后的当事人对象

        Raises:
            NotFoundError: 当事人不存在
            ValidationException: 数据验证失败
        """
        return cast(
            CaseParty,
            self.mutation_facade.update_party(
                party_id=party_id,
                data=data,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def delete_party(
        self,
        party_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        """
        删除当事人

        Args:
            party_id: 当事人 ID
            user: 当前用户

        Returns:
            {"success": True}

        Raises:
            NotFoundError: 当事人不存在
        """
        return cast(
            dict[str, bool],
            self.mutation_facade.delete_party(
                party_id=party_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def create_party_internal(self, case_id: int, client_id: int, legal_status: str | None = None) -> bool:
        return self.mutation_facade.create_party_internal(
            case_id=case_id, client_id=client_id, legal_status=legal_status
        )
