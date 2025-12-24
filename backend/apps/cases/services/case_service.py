"""
案件服务层
处理案件相关的业务逻辑
"""
import re
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass
from datetime import datetime
from django.db import transaction
from django.db.models import Q, QuerySet
import logging

from apps.core.exceptions import NotFoundError, ForbiddenError, ConflictError, ValidationException
from apps.core import business_config
from apps.core.interfaces import IContractService, ContractDTO, CaseDTO
from ..models import Case, CaseParty, CaseAssignment, CaseLog, CaseNumber

logger = logging.getLogger("apps.cases")


def normalize_case_number(number: str) -> str:
    """
    规范化案号用于搜索

    处理规则：
    1. 英文括号 () 转中文括号 （）
    2. 六角括号 〔〕 转中文括号 （）
    3. 中括号 [] 转中文括号 （）
    4. 删除所有空格（包括全角空格）
    5. 如果不以"号"结尾，自动补全

    Args:
        number: 原始案号

    Returns:
        规范化后的案号
    """
    if not number:
        return ""

    # 统一括号：英文、六角、中括号 -> 中文括号
    result = number.replace("(", "（").replace(")", "）")
    result = result.replace("〔", "（").replace("〕", "）")
    result = result.replace("[", "（").replace("]", "）")

    # 删除所有空格
    result = result.replace(" ", "").replace("\u3000", "")

    # 自动补全"号"字
    if result and not result.endswith("号"):
        result += "号"

    return result


def create_case_number_search_pattern(number: str) -> str:
    """
    创建案号搜索模式（用于模糊匹配）

    将括号替换为通配符，支持不同括号类型的匹配

    Args:
        number: 规范化后的案号

    Returns:
        搜索模式
    """
    if not number:
        return ""

    # 将括号替换为占位符，用于模糊匹配
    # 这样 （2025） 可以匹配 〔2025〕 或 [2025] 等
    pattern = number.replace("（", "_LBRACKET_").replace("）", "_RBRACKET_")
    return pattern


@dataclass
class CaseCreateData:
    """案件创建数据"""
    name: str
    contract_id: Optional[int] = None
    is_archived: bool = False
    hearing_institution: Optional[str] = None
    target_amount: Optional[float] = None
    cause_of_action: Optional[str] = None
    current_stage: Optional[str] = None
    effective_date: Optional[str] = None


@dataclass
class CaseFullCreateData:
    """完整案件创建数据"""
    case: CaseCreateData
    parties: Optional[List[Dict[str, Any]]] = None
    assignments: Optional[List[Dict[str, Any]]] = None
    logs: Optional[List[Dict[str, Any]]] = None


class CaseService:
    """
    案件服务

    职责：
    1. 封装案件相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 协调多个 Model 操作
    5. 通过 Protocol 跨模块通信
    """

    def __init__(
        self,
        contract_service: Optional[IContractService] = None
    ):
        """
        初始化服务（依赖注入）

        Args:
            contract_service: 合同服务接口（注入）
        """
        self.contract_service = contract_service

    @staticmethod
    def get_case_queryset() -> QuerySet:
        """
        获取带预加载的案件查询集

        优化点：
        1. 使用 select_related 预加载外键关系（contract）
        2. 使用 prefetch_related 预加载多对多和反向外键关系
        3. 深层预加载（assignments__lawyer__law_firm）
        4. 预加载合同的补充协议及其当事人（需求 4.1, 4.5）

        Returns:
            优化后的案件查询集
        """
        return Case.objects.select_related(
            "contract",  # 外键：合同
        ).prefetch_related(
            "parties__client",  # 反向外键 + 外键：当事人及其客户
            "assignments__lawyer",  # 反向外键 + 外键：指派及其律师
            "assignments__lawyer__law_firm",  # 深层预加载：律师的律所
            "logs__attachments",  # 反向外键 + 反向外键：日志及其附件
            "case_numbers",  # 反向外键：案号
            "supervising_authorities",  # 反向外键：主管机关
            "contract__supplementary_agreements__parties__client",  # 合同的补充协议及其当事人
        )

    def search_by_case_number(
        self,
        case_number: str,
        user: Optional[Any] = None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
        exact_match: bool = False,
    ) -> QuerySet:
        """
        通过案号搜索案件

        Args:
            case_number: 案号（支持各种格式）
            user: 当前用户
            org_access: 组织访问权限
            perm_open_access: 是否开放访问
            exact_match: 是否精确匹配

        Returns:
            匹配的案件查询集
        """
        # 规范化输入的案号
        normalized = normalize_case_number(case_number)
        if not normalized:
            return Case.objects.none()

        # 构建搜索条件
        # 由于数据库中的案号已经规范化存储，直接匹配即可
        if exact_match:
            # 精确匹配
            case_ids = CaseNumber.objects.filter(
                number=normalized
            ).values_list("case_id", flat=True)
        else:
            # 模糊匹配：去掉"号"字后进行 contains 搜索
            search_term = normalized.rstrip("号")
            case_ids = CaseNumber.objects.filter(
                number__icontains=search_term
            ).values_list("case_id", flat=True)

        # 获取案件并应用权限过滤
        qs = self.get_case_queryset().filter(id__in=case_ids)

        # 权限控制
        if perm_open_access:
            return qs

        if user and getattr(user, "is_authenticated", False):
            if getattr(user, "is_admin", False):
                return qs

            if org_access:
                lawyers = org_access.get("lawyers", set())
                extra_cases = org_access.get("extra_cases", set())

                qs = qs.filter(
                    Q(assignments__lawyer_id__in=list(lawyers)) |
                    Q(id__in=list(extra_cases))
                ).distinct()

        return qs

    def list_cases(
        self,
        case_type: Optional[str] = None,
        status: Optional[str] = None,
        user: Optional[Any] = None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
    ) -> QuerySet:
        """
        获取案件列表（优化查询）

        优化点：
        1. 使用 get_case_queryset() 预加载所有关联数据
        2. 使用 select_related 预加载 contract（用于过滤）
        3. 避免 N+1 查询问题

        Args:
            case_type: 案件类型过滤
            status: 状态过滤
            user: 当前用户
            org_access: 组织访问权限
            perm_open_access: 是否开放访问

        Returns:
            案件查询集
        """
        # 使用优化的查询集
        qs = self.get_case_queryset().order_by("-id")

        # 应用过滤条件
        if case_type:
            qs = qs.filter(contract__case_type=case_type)
        if status:
            qs = qs.filter(contract__status=status)

        # 权限控制
        if perm_open_access:
            return qs

        if user and getattr(user, "is_authenticated", False):
            if getattr(user, "is_admin", False):
                return qs

            if org_access:
                lawyers = org_access.get("lawyers", set())
                extra_cases = org_access.get("extra_cases", set())

                # 使用 distinct() 避免重复记录
                qs = qs.filter(
                    Q(assignments__lawyer_id__in=list(lawyers))
                ).distinct() | Case.objects.filter(id__in=list(extra_cases))

        return qs

    def get_case(
        self,
        case_id: int,
        user: Optional[Any] = None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
    ) -> Case:
        """
        获取单个案件（优化查询）

        优化点：
        1. 使用 get_case_queryset() 预加载所有关联数据
        2. 避免后续访问关联对象时产生额外查询

        Args:
            case_id: 案件 ID
            user: 当前用户
            org_access: 组织访问权限
            perm_open_access: 是否开放访问

        Returns:
            案件对象

        Raises:
            NotFoundError: 案件不存在
            ForbiddenError: 无权限访问
        """
        try:
            # 使用优化的查询集
            case = self.get_case_queryset().get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在")

        # 权限检查
        if perm_open_access:
            return case

        if user and getattr(user, "is_authenticated", False):
            if getattr(user, "is_admin", False):
                return case

            if self.check_case_access(case, user, org_access):
                return case

        raise ForbiddenError("无权限访问此案件")

    def check_case_access(
        self,
        case: Case,
        user: Any,
        org_access: Optional[Dict],
    ) -> bool:
        """
        检查用户是否有权访问案件

        Args:
            case: 案件对象
            user: 用户对象
            org_access: 组织访问权限

        Returns:
            是否有权限
        """
        if getattr(user, "is_admin", False):
            return True

        if not org_access:
            return False

        # 检查额外授权
        extra_cases = org_access.get("extra_cases", set())
        if case.id in extra_cases:
            return True

        # 检查团队成员或直接指派
        lawyers = org_access.get("lawyers", set())
        user_id = getattr(user, "id", None)

        return case.assignments.filter(
            Q(lawyer_id__in=list(lawyers)) | Q(lawyer_id=user_id)
        ).exists()

    def create_case(self, data: Dict[str, Any], user: Optional[Any] = None) -> Case:
        """
        创建案件

        Args:
            data: 案件数据
            user: 当前用户（用于权限检查）

        Returns:
            创建的案件对象

        Raises:
            ValidationException: 数据验证失败
            ForbiddenError: 权限不足
        """
        # 权限检查：用户必须已认证
        if user and not getattr(user, "is_authenticated", False):
            raise ForbiddenError("用户未认证")

        # 验证合同（如果提供了 contract_id）
        contract_id = data.get("contract_id")
        if contract_id and self.contract_service:
            contract = self.contract_service.get_contract(contract_id)
            if not contract:
                raise ValidationException(
                    message="合同不存在",
                    code="CONTRACT_NOT_FOUND",
                    errors={"contract_id": f"无效的合同 ID: {contract_id}"}
                )

            # 验证合同是否有效
            if not self.contract_service.validate_contract_active(contract_id):
                raise ValidationException(
                    message="合同未激活",
                    code="CONTRACT_INACTIVE",
                    errors={"contract_id": "合同状态不是 active"}
                )

        # 验证阶段
        current_stage = data.get("current_stage")
        if current_stage:
            # 如果有合同，获取合同的案件类型和代理阶段
            case_type = None
            rep_stages = None
            if contract_id and self.contract_service:
                contract = self.contract_service.get_contract(contract_id)
                if contract:
                    case_type = contract.case_type
                    rep_stages = contract.representation_stages

            data["current_stage"] = self._validate_stage(current_stage, case_type, rep_stages)

        logger.info(
            f"创建案件",
            extra={
                "action": "create_case",
                "case_name": data.get("name"),
                "contract_id": contract_id,
                "user_id": getattr(user, "id", None) if user else None
            }
        )

        return Case.objects.create(**data)

    def update_case(self, case_id: int, data: Dict[str, Any], user: Optional[Any] = None) -> Case:
        """
        更新案件

        Args:
            case_id: 案件 ID
            data: 更新数据
            user: 当前用户（用于权限检查）

        Returns:
            更新后的案件对象

        Raises:
            NotFoundError: 案件不存在
            ValidationException: 数据验证失败
            ForbiddenError: 权限不足
        """
        try:
            case = Case.objects.select_related("contract").get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在")

        # 权限检查：用户必须已认证
        if user and not getattr(user, "is_authenticated", False):
            raise ForbiddenError("用户未认证")

        # 验证合同（如果更新了 contract_id）
        contract_id = data.get("contract_id")
        if contract_id and self.contract_service:
            contract = self.contract_service.get_contract(contract_id)
            if not contract:
                raise ValidationException(
                    message="合同不存在",
                    code="CONTRACT_NOT_FOUND",
                    errors={"contract_id": f"无效的合同 ID: {contract_id}"}
                )

        # 验证阶段
        current_stage = data.get("current_stage")
        if current_stage:
            # 获取案件类型和代理阶段
            case_type = None
            rep_stages = None

            # 优先使用更新后的 contract_id
            check_contract_id = contract_id if contract_id else case.contract_id

            if check_contract_id and self.contract_service:
                contract = self.contract_service.get_contract(check_contract_id)
                if contract:
                    case_type = contract.case_type
                    rep_stages = contract.representation_stages

            data["current_stage"] = self._validate_stage(
                current_stage, case_type, rep_stages
            )

        for key, value in data.items():
            setattr(case, key, value)

        case.save()

        logger.info(
            f"更新案件成功",
            extra={
                "action": "update_case",
                "case_id": case_id,
                "user_id": getattr(user, "id", None) if user else None
            }
        )

        return case

    def delete_case(self, case_id: int, user: Optional[Any] = None) -> bool:
        """
        删除案件

        Args:
            case_id: 案件 ID
            user: 当前用户（用于权限检查）

        Returns:
            是否成功

        Raises:
            NotFoundError: 案件不存在
            ForbiddenError: 权限不足
        """
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在")

        # 权限检查：用户必须已认证
        if user and not getattr(user, "is_authenticated", False):
            raise ForbiddenError("用户未认证")

        logger.info(
            f"删除案件",
            extra={
                "action": "delete_case",
                "case_id": case_id,
                "user_id": getattr(user, "id", None) if user else None
            }
        )

        case.delete()
        return True

    def _validate_stage(
        self,
        stage: str,
        case_type: Optional[str],
        representation_stages: Optional[List[str]] = None,
    ) -> str:
        """
        验证案件阶段（私有方法）

        Args:
            stage: 阶段代码
            case_type: 案件类型
            representation_stages: 代理阶段列表

        Returns:
            验证后的阶段代码

        Raises:
            ValidationException: 验证失败
        """
        # 检查阶段是否适用于案件类型
        if case_type and not business_config.is_stage_valid_for_case_type(stage, case_type):
            raise ValidationException(
                "该案件类型不支持此阶段",
                errors={"current_stage": "阶段不适用于此案件类型"}
            )

        # 检查是否在代理阶段范围内
        if representation_stages and stage not in representation_stages:
            raise ValidationException(
                "当前阶段必须属于代理阶段集合",
                errors={"current_stage": "阶段不在代理范围内"}
            )

        return stage

    @transaction.atomic
    def create_case_full(
        self,
        data: Dict[str, Any],
        actor_id: Optional[int] = None,
        user: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        创建完整案件（包含当事人、指派、日志）

        Args:
            data: 完整案件数据
            actor_id: 操作人 ID
            user: 当前用户（用于权限检查）

        Returns:
            创建结果

        Raises:
            ValidationException: 数据验证失败
            ConflictError: 数据冲突
            ForbiddenError: 权限不足
        """
        case_data = data.get("case", {})
        parties_data = data.get("parties", [])
        assignments_data = data.get("assignments", [])
        logs_data = data.get("logs", [])
        supervising_authorities_data = data.get("supervising_authorities", [])

        # 创建案件（传递 user 参数进行权限检查）
        case = self.create_case(case_data, user=user)

        # 创建当事人关联
        parties = []
        for party in parties_data:
            if CaseParty.objects.filter(case=case, client_id=party["client_id"]).exists():
                raise ConflictError("该当事人已存在于此案件")

            parties.append(CaseParty.objects.create(
                case=case,
                client_id=party["client_id"],
                legal_status=party.get("legal_status"),
            ))

        # 创建律师指派
        assignments = []
        for assignment in assignments_data:
            assignments.append(CaseAssignment.objects.create(
                case=case,
                lawyer_id=assignment["lawyer_id"],
            ))

        # 创建日志
        logs = []
        for log in logs_data:
            reminder_time = log.get("reminder_time")
            if reminder_time and isinstance(reminder_time, str):
                try:
                    reminder_time = datetime.fromisoformat(reminder_time)
                except ValueError:
                    reminder_time = datetime.strptime(reminder_time, "%Y-%m-%d %H:%M:%S")

            logs.append(CaseLog.objects.create(
                case=case,
                content=log["content"],
                reminder_type=log.get("reminder_type"),
                reminder_time=reminder_time,
                actor_id=actor_id,
            ))

        # 创建主管机关
        supervising_authorities = []
        for authority in supervising_authorities_data:
            from ..models import SupervisingAuthority
            supervising_authorities.append(SupervisingAuthority.objects.create(
                case=case,
                name=authority.get("name"),
                authority_type=authority.get("authority_type"),
            ))

        return {
            "case": case,
            "parties": parties,
            "assignments": assignments,
            "logs": logs,
            "supervising_authorities": supervising_authorities,
        }



class CaseServiceAdapter:
    """
    案件服务适配器
    实现跨模块接口，将 Model 转换为 DTO
    """

    def __init__(self, contract_service: Optional[IContractService] = None):
        """
        初始化适配器

        Args:
            contract_service: 合同服务接口（可选）
        """
        self.service = CaseService(contract_service=contract_service)

    def _to_dto(self, case: Case) -> CaseDTO:
        """
        将 Model 转换为 DTO

        Args:
            case: Case Model 实例

        Returns:
            CaseDTO 实例
        """
        return CaseDTO(
            id=case.id,
            name=case.name,
            current_stage=case.current_stage,
            contract_id=case.contract_id,
            status=case.status if hasattr(case, 'status') else "active",
            case_type=case.case_type if hasattr(case, 'case_type') else None,
            cause_of_action=case.cause_of_action if hasattr(case, 'cause_of_action') else None,
            target_amount=case.target_amount if hasattr(case, 'target_amount') else None,
            is_archived=case.is_archived if hasattr(case, 'is_archived') else False,
            start_date=str(case.start_date) if hasattr(case, 'start_date') and case.start_date else None,
            effective_date=str(case.effective_date) if hasattr(case, 'effective_date') and case.effective_date else None,
        )

    def get_case(self, case_id: int) -> Optional[CaseDTO]:
        """
        获取案件信息

        Args:
            case_id: 案件 ID

        Returns:
            案件 DTO，不存在时返回 None
        """
        try:
            case = Case.objects.select_related("contract").get(id=case_id)
            return self._to_dto(case)
        except Case.DoesNotExist:
            return None

    def get_cases_by_contract(self, contract_id: int) -> List[CaseDTO]:
        """
        获取合同关联的案件

        Args:
            contract_id: 合同 ID

        Returns:
            案件 DTO 列表
        """
        cases = Case.objects.filter(contract_id=contract_id).select_related("contract")
        return [self._to_dto(case) for case in cases]

    def check_case_access(self, case_id: int, user_id: int) -> bool:
        """
        检查用户是否有权限访问案件

        Args:
            case_id: 案件 ID
            user_id: 用户 ID

        Returns:
            是否有权限访问
        """
        try:
            case = Case.objects.get(id=case_id)
            # 简化的权限检查：检查是否有指派记录
            return case.assignments.filter(lawyer_id=user_id).exists()
        except Case.DoesNotExist:
            return False

    def get_cases_by_ids(self, case_ids: List[int]) -> List[CaseDTO]:
        """
        批量获取案件信息

        Args:
            case_ids: 案件 ID 列表

        Returns:
            案件 DTO 列表
        """
        cases = Case.objects.filter(id__in=case_ids).select_related("contract")
        return [self._to_dto(case) for case in cases]

    def validate_case_active(self, case_id: int) -> bool:
        """
        验证案件是否有效（状态为 active）

        Args:
            case_id: 案件 ID

        Returns:
            案件是否有效
        """
        return Case.objects.filter(
            id=case_id,
            status="active"
        ).exists()

    def get_case_current_stage(self, case_id: int) -> Optional[str]:
        """
        获取案件的当前阶段

        Args:
            case_id: 案件 ID

        Returns:
            当前阶段，案件不存在时返回 None
        """
        try:
            case = Case.objects.only("current_stage").get(id=case_id)
            return case.current_stage
        except Case.DoesNotExist:
            return None

    def create_case(self, data: Dict[str, Any]) -> CaseDTO:
        """
        创建案件并返回 DTO

        Args:
            data: 案件数据字典

        Returns:
            创建的案件 DTO
        """
        case = self.service.create_case(data)
        return self._to_dto(case)

    def create_case_assignment(self, case_id: int, lawyer_id: int) -> bool:
        """
        创建案件指派

        Args:
            case_id: 案件 ID
            lawyer_id: 律师 ID

        Returns:
            是否创建成功
        """
        try:
            # 检查案件是否存在
            case = Case.objects.get(id=case_id)

            # 检查是否已存在相同的指派
            if CaseAssignment.objects.filter(case_id=case_id, lawyer_id=lawyer_id).exists():
                logger.warning(
                    f"案件指派已存在",
                    extra={
                        "action": "create_case_assignment",
                        "case_id": case_id,
                        "lawyer_id": lawyer_id,
                        "status": "already_exists"
                    }
                )
                return True  # 已存在视为成功

            # 创建指派
            CaseAssignment.objects.create(case=case, lawyer_id=lawyer_id)

            logger.info(
                f"创建案件指派成功",
                extra={
                    "action": "create_case_assignment",
                    "case_id": case_id,
                    "lawyer_id": lawyer_id
                }
            )
            return True
        except Case.DoesNotExist:
            logger.error(
                f"创建案件指派失败：案件不存在",
                extra={
                    "action": "create_case_assignment",
                    "case_id": case_id,
                    "lawyer_id": lawyer_id,
                    "error": "case_not_found"
                }
            )
            return False
        except Exception as e:
            logger.error(
                f"创建案件指派失败：{e}",
                extra={
                    "action": "create_case_assignment",
                    "case_id": case_id,
                    "lawyer_id": lawyer_id,
                    "error": str(e)
                }
            )
            return False

    def create_case_party(self, case_id: int, client_id: int, legal_status: Optional[str] = None) -> bool:
        """
        创建案件当事人

        Args:
            case_id: 案件 ID
            client_id: 客户 ID
            legal_status: 诉讼地位（可选）

        Returns:
            是否创建成功
        """
        try:
            # 检查案件是否存在
            case = Case.objects.get(id=case_id)

            # 检查是否已存在相同的当事人
            if CaseParty.objects.filter(case_id=case_id, client_id=client_id).exists():
                logger.warning(
                    f"案件当事人已存在",
                    extra={
                        "action": "create_case_party",
                        "case_id": case_id,
                        "client_id": client_id,
                        "status": "already_exists"
                    }
                )
                return True  # 已存在视为成功

            # 创建当事人
            CaseParty.objects.create(
                case=case,
                client_id=client_id,
                legal_status=legal_status
            )

            logger.info(
                f"创建案件当事人成功",
                extra={
                    "action": "create_case_party",
                    "case_id": case_id,
                    "client_id": client_id,
                    "legal_status": legal_status
                }
            )
            return True
        except Case.DoesNotExist:
            logger.error(
                f"创建案件当事人失败：案件不存在",
                extra={
                    "action": "create_case_party",
                    "case_id": case_id,
                    "client_id": client_id,
                    "error": "case_not_found"
                }
            )
            return False
        except Exception as e:
            logger.error(
                f"创建案件当事人失败：{e}",
                extra={
                    "action": "create_case_party",
                    "case_id": case_id,
                    "client_id": client_id,
                    "error": str(e)
                }
            )
            return False

    def get_user_extra_case_access(self, user_id: int) -> List[int]:
        """
        获取用户的额外案件访问授权

        Args:
            user_id: 用户 ID

        Returns:
            用户有额外访问权限的案件 ID 列表
        """
        from ..models import CaseAccessGrant
        
        try:
            case_ids = list(
                CaseAccessGrant.objects
                .filter(grantee_id=user_id)
                .values_list("case_id", flat=True)
            )
            
            logger.debug(
                f"获取用户额外案件访问权限",
                extra={
                    "action": "get_user_extra_case_access",
                    "user_id": user_id,
                    "case_count": len(case_ids)
                }
            )
            
            return case_ids
        except Exception as e:
            logger.error(
                f"获取用户额外案件访问权限失败：{e}",
                extra={
                    "action": "get_user_extra_case_access",
                    "user_id": user_id,
                    "error": str(e)
                }
            )
            return []

    def get_case_by_id_internal(self, case_id: int) -> Optional[CaseDTO]:
        """
        内部方法：获取案件信息（无权限检查）
        
        Args:
            case_id: 案件 ID
            
        Returns:
            案件 DTO，不存在时返回 None
        """
        try:
            case = Case.objects.select_related("contract").get(id=case_id)
            return self._to_dto(case)
        except Case.DoesNotExist:
            return None

    def search_cases_by_party_internal(
        self, 
        party_names: List[str], 
        status: Optional[str] = None
    ) -> List[CaseDTO]:
        """
        内部方法：根据当事人名称搜索案件
        
        Args:
            party_names: 当事人名称列表
            status: 案件状态筛选（可选）
            
        Returns:
            匹配的案件 DTO 列表
        """
        if not party_names:
            return []
        
        # 构建查询条件
        query = Q()
        for name in party_names:
            query |= Q(parties__client__name__icontains=name)
        
        # 获取案件查询集
        qs = Case.objects.select_related("contract").prefetch_related(
            "parties__client"
        ).filter(query).distinct()
        
        # 应用状态过滤
        if status:
            qs = qs.filter(status=status)
        
        return [self._to_dto(case) for case in qs]

    def get_case_numbers_by_case_internal(self, case_id: int) -> List[str]:
        """
        内部方法：获取案件的所有案号
        
        Args:
            case_id: 案件 ID
            
        Returns:
            案号字符串列表
        """
        try:
            case_numbers = CaseNumber.objects.filter(case_id=case_id).values_list("number", flat=True)
            return list(case_numbers)
        except Exception as e:
            logger.error(
                f"获取案件案号失败：{e}",
                extra={
                    "action": "get_case_numbers_by_case_internal",
                    "case_id": case_id,
                    "error": str(e)
                }
            )
            return []

    def get_case_party_names_internal(self, case_id: int) -> List[str]:
        """
        内部方法：获取案件的所有当事人名称
        
        Args:
            case_id: 案件 ID
            
        Returns:
            当事人名称列表
        """
        try:
            party_names = CaseParty.objects.filter(
                case_id=case_id
            ).select_related('client').values_list('client__name', flat=True)
            return [name for name in party_names if name]
        except Exception as e:
            logger.error(
                f"获取案件当事人失败：{e}",
                extra={
                    "action": "get_case_party_names_internal",
                    "case_id": case_id,
                    "error": str(e)
                }
            )
            return []

    def search_cases_by_case_number_internal(
        self, 
        case_number: str
    ) -> List[CaseDTO]:
        """
        内部方法：根据案号搜索案件
        
        Args:
            case_number: 案号字符串
            
        Returns:
            匹配的案件 DTO 列表
        """
        if not case_number:
            return []
        
        # 规范化案号
        normalized = normalize_case_number(case_number)
        if not normalized:
            return []
        
        # 查找匹配的案件ID
        case_ids = CaseNumber.objects.filter(
            number__icontains=normalized.rstrip("号")
        ).values_list("case_id", flat=True)
        
        if not case_ids:
            return []
        
        # 获取案件
        cases = Case.objects.select_related("contract").filter(id__in=case_ids)
        return [self._to_dto(case) for case in cases]

    def create_case_log_internal(
        self,
        case_id: int,
        content: str,
        user_id: Optional[int] = None
    ) -> int:
        """
        内部方法：创建案件日志，返回日志ID
        
        Args:
            case_id: 案件 ID
            content: 日志内容
            user_id: 用户 ID（可选）
            
        Returns:
            创建的日志 ID
            
        Raises:
            NotFoundError: 案件不存在
        """
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在")
        
        case_log = CaseLog.objects.create(
            case=case,
            content=content,
            actor_id=user_id
        )
        
        logger.info(
            f"创建案件日志成功",
            extra={
                "action": "create_case_log_internal",
                "case_id": case_id,
                "log_id": case_log.id,
                "user_id": user_id
            }
        )
        
        return case_log.id

    def add_case_log_attachment_internal(
        self,
        case_log_id: int,
        file_path: str,
        file_name: str
    ) -> bool:
        """
        内部方法：添加案件日志附件
        
        Args:
            case_log_id: 案件日志 ID
            file_path: 文件路径
            file_name: 文件名称
            
        Returns:
            是否添加成功
            
        Raises:
            NotFoundError: 案件日志不存在
        """
        try:
            case_log = CaseLog.objects.get(id=case_log_id)
        except CaseLog.DoesNotExist:
            raise NotFoundError(f"案件日志 {case_log_id} 不存在")
        
        try:
            from ..models import CaseLogAttachment
            # CaseLogAttachment 模型字段是 log 和 file
            # file 是 FileField，需要设置文件路径
            attachment = CaseLogAttachment(log=case_log)
            attachment.file.name = file_path  # 直接设置文件路径（相对于 MEDIA_ROOT）
            attachment.save()
            
            logger.info(
                f"添加案件日志附件成功",
                extra={
                    "action": "add_case_log_attachment_internal",
                    "case_log_id": case_log_id,
                    "file_name": file_name
                }
            )
            
            return True
        except Exception as e:
            logger.error(
                f"添加案件日志附件失败：{e}",
                extra={
                    "action": "add_case_log_attachment_internal",
                    "case_log_id": case_log_id,
                    "file_name": file_name,
                    "error": str(e)
                }
            )
            return False

    def add_case_number_internal(
        self,
        case_id: int,
        case_number: str,
        user_id: Optional[int] = None
    ) -> bool:
        """
        内部方法：为案件添加案号（如果不存在）
        
        Args:
            case_id: 案件 ID
            case_number: 案号字符串
            user_id: 操作用户 ID（可选）
            
        Returns:
            是否添加成功（已存在也返回 True）
        """
        if not case_number or not case_number.strip():
            return False
        
        # 规范化案号
        normalized = normalize_case_number(case_number)
        if not normalized:
            return False
        
        try:
            # 检查案件是否存在
            case = Case.objects.get(id=case_id)
            
            # 检查案号是否已存在（规范化后比较）
            existing_numbers = CaseNumber.objects.filter(case_id=case_id)
            for existing in existing_numbers:
                if normalize_case_number(existing.number) == normalized:
                    logger.info(
                        f"案号已存在，跳过添加",
                        extra={
                            "action": "add_case_number_internal",
                            "case_id": case_id,
                            "case_number": case_number,
                            "normalized": normalized
                        }
                    )
                    return True
            
            # 创建新案号
            CaseNumber.objects.create(
                case=case,
                number=normalized
            )
            
            logger.info(
                f"添加案号成功",
                extra={
                    "action": "add_case_number_internal",
                    "case_id": case_id,
                    "case_number": case_number,
                    "normalized": normalized,
                    "user_id": user_id
                }
            )
            return True
            
        except Case.DoesNotExist:
            logger.error(
                f"添加案号失败：案件不存在",
                extra={
                    "action": "add_case_number_internal",
                    "case_id": case_id,
                    "case_number": case_number
                }
            )
            return False
        except Exception as e:
            logger.error(
                f"添加案号失败：{e}",
                extra={
                    "action": "add_case_number_internal",
                    "case_id": case_id,
                    "case_number": case_number,
                    "error": str(e)
                }
            )
            return False
