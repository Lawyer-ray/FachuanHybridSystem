"""
合同服务层
处理合同相关的业务逻辑
"""
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from decimal import Decimal
from django.db import transaction
from django.db.models import QuerySet, Sum
import logging

from apps.core.exceptions import NotFoundError, ValidationException, PermissionDenied
from apps.core import business_config
from apps.core.business_config import BusinessConfig
from ..models import Contract, ContractParty, ContractAssignment, FeeMode

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService
    from .contract_payment_service import ContractPaymentService
    from .supplementary_agreement_service import SupplementaryAgreementService

logger = logging.getLogger("apps.contracts")


class ContractService:
    """
    合同服务

    职责：
    1. 封装合同相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 协调多个 Model 操作
    5. 优化数据库查询
    """

    def __init__(
        self,
        config: Optional[BusinessConfig] = None,
        case_service: Optional["ICaseService"] = None,
        lawyer_assignment_service: Optional["LawyerAssignmentService"] = None,
        payment_service: Optional["ContractPaymentService"] = None,
        supplementary_agreement_service: Optional["SupplementaryAgreementService"] = None,
    ):
        """
        初始化服务（依赖注入）

        Args:
            config: 业务配置对象（可选，有默认值）
            case_service: 案件服务接口（可选，延迟获取）
            lawyer_assignment_service: 律师指派服务（可选，延迟获取）
            payment_service: 收款服务（可选，延迟获取）
            supplementary_agreement_service: 补充协议服务（可选，延迟获取）
        """
        self.config = config or business_config
        self._case_service = case_service
        self._lawyer_assignment_service = lawyer_assignment_service
        self._payment_service = payment_service
        self._supplementary_agreement_service = supplementary_agreement_service

    @property
    def case_service(self) -> "ICaseService":
        """
        延迟获取案件服务

        Returns:
            ICaseService 实例
        """
        if self._case_service is None:
            from apps.core.interfaces import ServiceLocator
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service

    @property
    def lawyer_assignment_service(self) -> "LawyerAssignmentService":
        """
        延迟获取律师指派服务

        Returns:
            LawyerAssignmentService 实例
        """
        if self._lawyer_assignment_service is None:
            from apps.core.interfaces import ServiceLocator
            from .lawyer_assignment_service import LawyerAssignmentService
            # 通过 ServiceLocator 获取 lawyer_service 并注入
            self._lawyer_assignment_service = LawyerAssignmentService(
                lawyer_service=ServiceLocator.get_lawyer_service()
            )
        return self._lawyer_assignment_service

    @property
    def payment_service(self) -> "ContractPaymentService":
        """
        延迟获取收款服务

        Returns:
            ContractPaymentService 实例
        """
        if self._payment_service is None:
            from .contract_payment_service import ContractPaymentService
            self._payment_service = ContractPaymentService()
        return self._payment_service

    @property
    def supplementary_agreement_service(self) -> "SupplementaryAgreementService":
        """
        延迟获取补充协议服务

        Returns:
            SupplementaryAgreementService 实例
        """
        if self._supplementary_agreement_service is None:
            from .supplementary_agreement_service import SupplementaryAgreementService
            from apps.client.services import ClientServiceAdapter
            self._supplementary_agreement_service = SupplementaryAgreementService(
                client_service=ClientServiceAdapter()
            )
        return self._supplementary_agreement_service

    def get_contract_queryset(self) -> QuerySet:
        """
        获取带预加载的合同查询集

        优化点：
        1. 使用 select_related 预加载外键关系
        2. 使用 prefetch_related 预加载多对多和反向外键关系

        Returns:
            优化后的合同查询集
        """
        return Contract.objects.prefetch_related(
            "cases",
            "contract_parties__client",
            "payments",
            "reminders",
            "assignments__lawyer",
            "assignments__lawyer__law_firm",
        )

    def list_contracts(
        self,
        case_type: Optional[str] = None,
        status: Optional[str] = None,
        is_archived: Optional[bool] = None,
        user: Optional[Any] = None,
        org_access: Optional[Dict[str, Any]] = None,
        perm_open_access: bool = False,
    ) -> QuerySet:
        """
        获取合同列表（包含权限过滤）

        Args:
            case_type: 案件类型过滤
            status: 状态过滤
            is_archived: 是否已归档过滤
            user: 当前用户对象
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            合同查询集
        """
        qs = self.get_contract_queryset().order_by("-id")

        # 基础过滤条件
        if case_type:
            qs = qs.filter(case_type=case_type)
        if status:
            qs = qs.filter(status=status)
        if is_archived is not None:
            qs = qs.filter(is_archived=is_archived)

        # 权限过滤逻辑
        if perm_open_access:
            return qs
        
        if user and getattr(user, "is_authenticated", False):
            if getattr(user, "is_admin", False):
                return qs
            
            if org_access:
                from django.db.models import Q
                user_id = getattr(user, "id", None)
                qs = qs.filter(
                    (
                        Q(assignments__lawyer_id__in=list(org_access["lawyers"]))
                        | Q(assignments__lawyer_id=user_id)
                        | Q(cases__assignments__lawyer_id=user_id)
                    )
                ).distinct()
        
        return qs

    def _get_contract_internal(self, contract_id: int) -> Contract:
        """
        内部获取合同（无权限检查）

        Args:
            contract_id: 合同 ID

        Returns:
            合同对象

        Raises:
            NotFoundError: 合同不存在
        """
        try:
            return self.get_contract_queryset().get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(f"合同 {contract_id} 不存在")

    def get_contract(
        self, 
        contract_id: int,
        user: Optional[Any] = None,
        org_access: Optional[Dict[str, Any]] = None,
        perm_open_access: bool = False,
    ) -> Contract:
        """
        获取单个合同（包含权限检查）

        Args:
            contract_id: 合同 ID
            user: 当前用户对象
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            合同对象

        Raises:
            NotFoundError: 合同不存在
            PermissionDenied: 无权限访问
        """
        contract = self._get_contract_internal(contract_id)

        # 权限检查逻辑
        if perm_open_access:
            return contract
        
        if user and getattr(user, "is_authenticated", False):
            if getattr(user, "is_admin", False):
                return contract
            
            # 团队成员可见，或被明确指派到合同/合同关联的案件
            user_id = getattr(user, "id", None)
            has_access = False
            
            if org_access:
                # 检查是否指派给该律师（通过 ContractAssignment）
                has_access = contract.assignments.filter(
                    lawyer_id__in=org_access.get("lawyers", set())
                ).exists() or contract.assignments.filter(lawyer_id=user_id).exists()
                
                if not has_access:
                    has_access = contract.cases.filter(assignments__lawyer_id=user_id).exists()
            
            if has_access:
                return contract
        
        raise PermissionDenied("无权限访问该合同")

    @transaction.atomic
    def create_contract(self, data: Dict[str, Any]) -> Contract:
        """
        创建合同

        Args:
            data: 合同数据（可包含 lawyer_ids）

        Returns:
            创建的合同对象

        Raises:
            ValidationException: 数据验证失败
        """
        # 提取 lawyer_ids（如果存在）
        lawyer_ids = data.pop("lawyer_ids", None)

        # 验证收费模式
        self._validate_fee_mode(data)

        # 验证代理阶段
        case_type = data.get("case_type")
        representation_stages = data.get("representation_stages", [])
        if representation_stages:
            data["representation_stages"] = self._validate_stages(
                representation_stages, case_type
            )

        contract = Contract.objects.create(**data)

        # 处理律师指派
        if lawyer_ids:
            self.lawyer_assignment_service.set_contract_lawyers(
                contract.id,
                lawyer_ids
            )

        logger.info(
            f"合同创建成功",
            extra={
                "contract_id": contract.id,
                "lawyer_ids": lawyer_ids,
                "action": "create_contract"
            }
        )

        return contract

    @transaction.atomic
    def update_contract(self, contract_id: int, data: Dict[str, Any]) -> Contract:
        """
        更新合同

        Args:
            contract_id: 合同 ID
            data: 更新数据

        Returns:
            更新后的合同对象

        Raises:
            NotFoundError: 合同不存在
            ValidationException: 数据验证失败
        """
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(f"合同 {contract_id} 不存在")

        # 如果更新收费模式，需要验证
        if "fee_mode" in data:
            merged_data = {**contract.__dict__, **data}
            self._validate_fee_mode(merged_data)

        # 验证代理阶段
        if "representation_stages" in data:
            case_type = data.get("case_type", contract.case_type)
            data["representation_stages"] = self._validate_stages(
                data["representation_stages"], case_type
            )

        for key, value in data.items():
            setattr(contract, key, value)

        contract.save()

        logger.info(
            f"合同更新成功",
            extra={
                "contract_id": contract_id,
                "action": "update_contract"
            }
        )

        return contract

    @transaction.atomic
    def delete_contract(self, contract_id: int) -> bool:
        """
        删除合同

        Args:
            contract_id: 合同 ID

        Returns:
            是否成功

        Raises:
            NotFoundError: 合同不存在
        """
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(f"合同 {contract_id} 不存在")

        contract.delete()

        logger.info(
            f"合同删除成功",
            extra={
                "contract_id": contract_id,
                "action": "delete_contract"
            }
        )

        return True

    def get_finance_summary(self, contract_id: int) -> Dict[str, Any]:
        """
        获取合同财务汇总

        Args:
            contract_id: 合同 ID

        Returns:
            财务汇总数据
        """
        contract = self._get_contract_internal(contract_id)

        # 计算收款和开票总额
        payments = contract.payments.all()
        total_received = sum(p.amount or Decimal(0) for p in payments)
        total_invoiced = sum(p.invoiced_amount or Decimal(0) for p in payments)

        # 计算未收金额
        unpaid = None
        if contract.fixed_amount:
            unpaid = max(Decimal(0), contract.fixed_amount - total_received)

        return {
            "contract_id": contract_id,
            "total_received": float(total_received),
            "total_invoiced": float(total_invoiced),
            "unpaid_amount": float(unpaid) if unpaid is not None else None,
            "payment_count": len(payments),
        }

    def add_party(self, contract_id: int, client_id: int) -> ContractParty:
        """
        添加合同当事人

        Args:
            contract_id: 合同 ID
            client_id: 客户 ID

        Returns:
            创建的当事人关联
        """
        if not Contract.objects.filter(id=contract_id).exists():
            raise NotFoundError(f"合同 {contract_id} 不存在")

        party, created = ContractParty.objects.get_or_create(
            contract_id=contract_id,
            client_id=client_id,
        )

        return party

    def remove_party(self, contract_id: int, client_id: int) -> bool:
        """
        移除合同当事人

        Args:
            contract_id: 合同 ID
            client_id: 客户 ID

        Returns:
            是否成功
        """
        deleted, _ = ContractParty.objects.filter(
            contract_id=contract_id,
            client_id=client_id,
        ).delete()

        return deleted > 0

    @transaction.atomic
    def update_contract_lawyers(
        self,
        contract_id: int,
        lawyer_ids: List[int]
    ) -> List[ContractAssignment]:
        """
        更新合同律师指派

        Args:
            contract_id: 合同 ID
            lawyer_ids: 律师 ID 列表（第一个为主办）

        Returns:
            更新后的 ContractAssignment 列表

        Raises:
            NotFoundError: 合同不存在
            ValidationException: lawyer_ids 为空或律师不存在/已停用
        """
        # 验证 lawyer_ids 非空
        if not lawyer_ids:
            raise ValidationException(
                "至少需要指派一个律师",
                code="EMPTY_LAWYER_IDS",
                errors={"lawyer_ids": "至少需要指派一个律师"}
            )

        # 调用 LawyerAssignmentService 处理指派逻辑
        assignments = self.lawyer_assignment_service.set_contract_lawyers(
            contract_id,
            lawyer_ids
        )

        logger.info(
            f"合同律师指派更新成功",
            extra={
                "contract_id": contract_id,
                "lawyer_ids": lawyer_ids,
                "action": "update_contract_lawyers"
            }
        )

        return assignments

    @transaction.atomic
    def create_contract_with_cases(
        self,
        contract_data: Dict[str, Any],
        cases_data: Optional[List[Dict[str, Any]]] = None,
        assigned_lawyer_ids: Optional[List[int]] = None,
        payments_data: Optional[List[Dict[str, Any]]] = None,
        confirm_finance: bool = False,
        user: Any = None,
    ) -> Contract:
        """
        创建合同并关联案件

        通过 ICaseService 接口创建案件，实现模块解耦。

        Args:
            contract_data: 合同数据（可包含 lawyer_ids）
            cases_data: 案件数据列表（可选）
            assigned_lawyer_ids: 指派律师 ID 列表（已废弃，使用 contract_data 中的 lawyer_ids）
            payments_data: 收款记录数据列表（可选）
            confirm_finance: 是否已确认财务操作
            user: 当前用户对象

        Returns:
            创建的合同对象

        Raises:
            ValidationException: 数据验证失败
        """
        # 添加收款记录需要确认
        if payments_data and not confirm_finance:
            raise ValidationException("关键财务操作需二次确认")

        # 提取补充协议数据
        supplementary_agreements_data = contract_data.pop("supplementary_agreements", None)
        
        # 提取 lawyer_ids（优先使用 contract_data 中的，回退到 assigned_lawyer_ids）
        lawyer_ids = contract_data.get("lawyer_ids") or assigned_lawyer_ids
        if lawyer_ids:
            contract_data["lawyer_ids"] = lawyer_ids
        
        # 创建合同（会自动处理 lawyer_ids）
        contract = self.create_contract(contract_data)
        
        # 创建补充协议（使用注入的服务实例）
        if supplementary_agreements_data:
            for sa_data in supplementary_agreements_data:
                self.supplementary_agreement_service.create_supplementary_agreement(
                    contract_id=contract.id,
                    name=sa_data.get("name"),
                    party_ids=sa_data.get("party_ids")
                )

        # 添加收款记录
        if payments_data:
            self.add_payments(
                contract_id=contract.id,
                payments_data=payments_data,
                user=user,
                confirm=True,  # 已在上层确认
            )

        # 创建关联案件（通过 ICaseService 接口）
        if cases_data:
            # 获取所有指派律师（通过新的服务）
            all_lawyers = self.lawyer_assignment_service.get_all_lawyers(contract.id)
            all_lawyer_ids = [lawyer.id for lawyer in all_lawyers]

            for case_data in cases_data:
                # 通过接口创建案件
                case_create_data = {
                    "name": case_data.get("name"),
                    "contract_id": contract.id,
                    "is_archived": case_data.get("is_archived", False),
                    "case_type": case_data.get("case_type"),
                    "target_amount": case_data.get("target_amount"),
                }
                case_dto = self.case_service.create_case(case_create_data)

                # 同步合同的多指派到案件（通过接口）
                for lawyer_id in all_lawyer_ids:
                    self.case_service.create_case_assignment(case_dto.id, lawyer_id)

                # 创建当事人（通过接口）
                parties = case_data.get("parties", [])
                for party_data in parties:
                    self.case_service.create_case_party(
                        case_id=case_dto.id,
                        client_id=party_data.get("client_id"),
                        legal_status=party_data.get("legal_status"),
                    )

        logger.info(
            f"合同及案件创建成功",
            extra={
                "contract_id": contract.id,
                "cases_count": len(cases_data) if cases_data else 0,
                "payments_count": len(payments_data) if payments_data else 0,
                "action": "create_contract_with_cases"
            }
        )

        return contract

    @transaction.atomic
    def update_contract_with_finance(
        self,
        contract_id: int,
        update_data: Dict[str, Any],
        user: Any = None,
        confirm_finance: bool = False,
        new_payments: Optional[List[Dict[str, Any]]] = None,
    ) -> Contract:
        """
        更新合同（包含财务数据验证）

        验证逻辑在 Service 层：
        1. 检查是否涉及财务字段
        2. 财务操作需要 confirm_finance=True
        3. 财务操作需要管理员权限

        Args:
            contract_id: 合同 ID
            update_data: 更新数据
            user: 当前用户对象
            confirm_finance: 是否已确认财务操作
            new_payments: 新增收款记录数据列表

        Returns:
            更新后的合同对象

        Raises:
            PermissionDenied: 权限不足
            ValidationException: 数据验证失败
        """
        contract = self._get_contract_internal(contract_id)

        # 提取补充协议数据
        supplementary_agreements_data = update_data.pop("supplementary_agreements", None)

        # 检查是否涉及财务字段
        finance_keys = {"fee_mode", "fixed_amount", "risk_rate", "custom_terms"}
        touch_finance = any(k in update_data for k in finance_keys)

        # 财务操作需要二次确认（验证在 Service 层）
        if touch_finance and not confirm_finance:
            raise ValidationException("关键财务操作需二次确认")

        # 添加收款记录也需要确认
        if new_payments and not confirm_finance:
            raise ValidationException("关键财务操作需二次确认")

        # 获取用户信息
        user_id = getattr(user, "id", None)
        is_admin = getattr(user, "is_admin", False)

        if touch_finance:
            # 财务数据修改需要管理员权限
            if not is_admin:
                raise PermissionDenied("修改财务数据需要管理员权限")

            # 记录旧的财务数据
            old_finance = {
                k: getattr(contract, k)
                for k in finance_keys
            }

        # 更新合同
        contract = self.update_contract(contract_id, update_data)
        
        # 更新补充协议（完全替换，使用注入的服务实例）
        if supplementary_agreements_data is not None:
            from ..models import SupplementaryAgreement
            
            # 删除现有的所有补充协议
            SupplementaryAgreement.objects.filter(contract_id=contract_id).delete()
            
            # 创建新的补充协议
            for sa_data in supplementary_agreements_data:
                self.supplementary_agreement_service.create_supplementary_agreement(
                    contract_id=contract.id,
                    name=sa_data.get("name"),
                    party_ids=sa_data.get("party_ids")
                )

        # 添加收款记录
        if new_payments:
            self.add_payments(
                contract_id=contract_id,
                payments_data=new_payments,
                user=user,
                confirm=True,  # 已在上层确认
            )

        # 记录财务变更日志
        if touch_finance:
            new_finance = {
                k: getattr(contract, k)
                for k in finance_keys
            }
            changes = {
                k: {"old": old_finance.get(k), "new": new_finance.get(k)}
                for k in finance_keys
                if old_finance.get(k) != new_finance.get(k)
            }

            if changes:
                self._log_finance_change(
                    contract_id=contract.id,
                    user_id=user_id,
                    action="update_contract_finance",
                    changes=changes
                )

        return contract

    @transaction.atomic
    def add_payments(
        self,
        contract_id: int,
        payments_data: List[Dict[str, Any]],
        user: Any = None,
        confirm: bool = True,
    ) -> List["ContractPayment"]:
        """
        添加合同收款记录（委托给 ContractPaymentService）

        Args:
            contract_id: 合同 ID
            payments_data: 收款数据列表
            user: 当前用户对象
            confirm: 是否已确认（默认 True，表示已在上层确认）

        Returns:
            创建的收款记录列表

        Raises:
            PermissionDenied: 权限不足
            ValidationException: 数据验证失败
        """
        from django.utils.dateparse import parse_date

        created_payments = []

        for payment_data in payments_data:
            # 解析收款日期
            received_at = None
            if payment_data.get("received_at"):
                received_at = parse_date(payment_data["received_at"])

            # 委托给 ContractPaymentService 创建收款记录
            payment = self.payment_service.create_payment(
                contract_id=contract_id,
                amount=Decimal(str(payment_data.get("amount", 0))),
                received_at=received_at,
                invoice_status=payment_data.get("invoice_status"),
                invoiced_amount=Decimal(str(payment_data.get("invoiced_amount", 0)))
                    if payment_data.get("invoiced_amount") is not None
                    else None,
                note=payment_data.get("note"),
                user=user,
                confirm=confirm,
            )
            created_payments.append(payment)

        logger.info(
            f"添加收款记录成功",
            extra={
                "contract_id": contract_id,
                "payment_count": len(created_payments),
                "action": "add_payments"
            }
        )

        return created_payments

    # ========== 私有方法（业务逻辑封装） ==========

    def _log_finance_change(
        self,
        contract_id: int,
        user_id: int,
        action: str,
        changes: Dict[str, Any],
        level: str = "INFO"
    ) -> None:
        """
        记录财务变更日志（私有方法）

        Args:
            contract_id: 合同 ID
            user_id: 操作用户 ID
            action: 操作类型
            changes: 变更内容
            level: 日志级别
        """
        try:
            from ..models import ContractFinanceLog
            ContractFinanceLog.objects.create(
                contract_id=contract_id,
                action=action,
                level=level,
                actor_id=user_id,
                payload=changes,
            )
        except Exception as e:
            logger.error(
                f"记录财务日志失败: {e}",
                extra={
                    "contract_id": contract_id,
                    "action": action
                }
            )

    def _validate_fee_mode(self, data: Dict[str, Any]) -> None:
        """
        验证收费模式数据（私有方法）

        Args:
            data: 合同数据

        Raises:
            ValidationException: 验证失败
        """
        fee_mode = data.get("fee_mode")
        fixed_amount = data.get("fixed_amount")
        risk_rate = data.get("risk_rate")
        custom_terms = data.get("custom_terms")

        errors = {}

        if fee_mode == FeeMode.FIXED:
            if not fixed_amount or float(fixed_amount) <= 0:
                errors["fixed_amount"] = "固定收费需填写金额"

        elif fee_mode == FeeMode.SEMI_RISK:
            if not fixed_amount or float(fixed_amount) <= 0:
                errors["fixed_amount"] = "半风险需填写前期金额"
            if not risk_rate or float(risk_rate) <= 0:
                errors["risk_rate"] = "半风险需填写风险比例"

        elif fee_mode == FeeMode.FULL_RISK:
            if not risk_rate or float(risk_rate) <= 0:
                errors["risk_rate"] = "全风险需填写风险比例"

        elif fee_mode == FeeMode.CUSTOM:
            if not custom_terms or not str(custom_terms).strip():
                errors["custom_terms"] = "自定义收费需填写条款文本"

        if errors:
            raise ValidationException("收费模式验证失败", errors=errors)

    def _validate_stages(self, stages: List[str], case_type: Optional[str]) -> List[str]:
        """
        验证代理阶段（私有方法）

        Args:
            stages: 阶段列表
            case_type: 案件类型

        Returns:
            验证后的阶段列表

        Raises:
            ValidationException: 验证失败
        """
        if not stages:
            return []

        valid_stages = [v for v, _ in self.config.get_stages_for_case_type(case_type)]
        invalid = set(stages) - set(valid_stages)

        if invalid:
            raise ValidationException(
                "无效的代理阶段",
                errors={"representation_stages": f"无效阶段: {', '.join(invalid)}"}
            )

        return stages

    def get_all_parties(self, contract_id: int) -> List[Dict[str, Any]]:
        """
        获取合同及其补充协议的所有当事人

        聚合 ContractParty 和 SupplementaryAgreementParty 中的所有 Client，
        按 client_id 去重，返回包含来源标识的当事人列表。

        Args:
            contract_id: 合同 ID

        Returns:
            当事人列表，每个元素包含:
            - id: Client ID
            - name: Client 名称
            - source: 来源 ("contract" 或 "supplementary")

        Raises:
            NotFoundError: 合同不存在

        Requirements: 2.1, 2.2, 2.3, 2.4
        """
        contract = self._get_contract_internal(contract_id)

        # 用于去重的字典，key 为 client_id
        parties_dict: Dict[int, Dict[str, Any]] = {}

        # 聚合合同当事人 (Requirements 2.2)
        for party in contract.contract_parties.select_related("client").all():
            client = party.client
            if client.id not in parties_dict:
                parties_dict[client.id] = {
                    "id": client.id,
                    "name": client.name,
                    "source": "contract",
                }

        # 聚合补充协议当事人 (Requirements 2.3)
        for sa in contract.supplementary_agreements.prefetch_related("parties__client").all():
            for sa_party in sa.parties.all():
                client = sa_party.client
                if client.id not in parties_dict:
                    parties_dict[client.id] = {
                        "id": client.id,
                        "name": client.name,
                        "source": "supplementary",
                    }

        # 返回去重后的列表 (Requirements 2.4)
        return list(parties_dict.values())


class ContractServiceAdapter:
    """
    合同服务适配器
    实现 IContractService Protocol，将 Model 转换为 DTO
    """

    def __init__(
        self,
        contract_service: Optional[ContractService] = None,
        case_service: Optional["ICaseService"] = None,
    ):
        """
        初始化适配器

        Args:
            contract_service: 合同服务实例（可选）
            case_service: 案件服务接口（可选，传递给 ContractService）
        """
        if contract_service is not None:
            self.contract_service = contract_service
        else:
            self.contract_service = ContractService(case_service=case_service)

    def _to_dto(self, contract: Contract) -> "ContractDTO":
        """
        将 Model 转换为 DTO

        Args:
            contract: Contract Model 实例

        Returns:
            ContractDTO 实例
        """
        from apps.core.interfaces import ContractDTO
        return ContractDTO.from_model(contract)

    def get_contract(self, contract_id: int) -> "Optional[ContractDTO]":
        """
        获取合同信息

        Args:
            contract_id: 合同 ID

        Returns:
            合同 DTO，不存在时返回 None
        """
        try:
            contract = self.contract_service._get_contract_internal(contract_id)
            return self._to_dto(contract)
        except NotFoundError:
            return None

    def get_contract_stages(self, contract_id: int) -> List[str]:
        """
        获取合同的代理阶段

        Args:
            contract_id: 合同 ID

        Returns:
            代理阶段列表
        """
        try:
            contract = self.contract_service._get_contract_internal(contract_id)
            return contract.representation_stages or []
        except NotFoundError:
            return []

    def validate_contract_active(self, contract_id: int) -> bool:
        """
        验证合同是否有效（状态为 active）

        Args:
            contract_id: 合同 ID

        Returns:
            合同是否有效
        """
        try:
            contract = self.contract_service._get_contract_internal(contract_id)
            return contract.status == "active"
        except NotFoundError:
            return False

    def get_contracts_by_ids(self, contract_ids: List[int]) -> List["ContractDTO"]:
        """
        批量获取合同信息

        Args:
            contract_ids: 合同 ID 列表

        Returns:
            合同 DTO 列表
        """
        contracts = Contract.objects.filter(id__in=contract_ids)
        return [self._to_dto(c) for c in contracts]

    def get_contract_assigned_lawyer_id(self, contract_id: int) -> Optional[int]:
        """
        获取合同的主办律师 ID（使用 primary_lawyer）

        Args:
            contract_id: 合同 ID

        Returns:
            主办律师 ID，合同不存在或无主办律师时返回 None
        """
        try:
            contract = self.contract_service._get_contract_internal(contract_id)
            primary_lawyer = contract.primary_lawyer
            return primary_lawyer.id if primary_lawyer else None
        except NotFoundError:
            return None

    def get_contract_lawyers(self, contract_id: int) -> List["LawyerDTO"]:
        """
        获取合同的所有律师

        Args:
            contract_id: 合同 ID

        Returns:
            律师 DTO 列表，按 is_primary 降序、order 升序排列

        Raises:
            NotFoundError: 合同不存在
        """
        from apps.core.interfaces import LawyerDTO
        
        contract = self.contract_service._get_contract_internal(contract_id)
        all_lawyers = contract.all_lawyers
        
        return [LawyerDTO.from_model(lawyer) for lawyer in all_lawyers]

    def get_all_parties(self, contract_id: int) -> List[Dict[str, Any]]:
        """
        获取合同及其补充协议的所有当事人

        聚合 ContractParty 和 SupplementaryAgreementParty 中的所有 Client，
        按 client_id 去重，返回包含来源标识的当事人列表。

        Args:
            contract_id: 合同 ID

        Returns:
            当事人列表，每个元素包含:
            - id: Client ID
            - name: Client 名称
            - source: 来源 ("contract" 或 "supplementary")

        Raises:
            NotFoundError: 合同不存在

        Requirements: 2.1, 2.2, 2.3, 2.4
        """
        contract = self.contract_service._get_contract_internal(contract_id)

        # 用于去重的字典，key 为 client_id
        parties_dict: Dict[int, Dict[str, Any]] = {}

        # 聚合合同当事人 (Requirements 2.2)
        for party in contract.contract_parties.select_related("client").all():
            client = party.client
            if client.id not in parties_dict:
                parties_dict[client.id] = {
                    "id": client.id,
                    "name": client.name,
                    "source": "contract",
                }

        # 聚合补充协议当事人 (Requirements 2.3)
        for sa in contract.supplementary_agreements.prefetch_related("parties__client").all():
            for sa_party in sa.parties.all():
                client = sa_party.client
                if client.id not in parties_dict:
                    parties_dict[client.id] = {
                        "id": client.id,
                        "name": client.name,
                        "source": "supplementary",
                    }

        # 返回去重后的列表 (Requirements 2.4)
        return list(parties_dict.values())
