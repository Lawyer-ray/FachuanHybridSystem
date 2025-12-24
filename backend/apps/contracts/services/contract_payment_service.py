"""
合同收款服务层
处理合同收款相关的业务逻辑，符合三层架构规范
"""
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import date
from django.db import transaction
from django.db.models import QuerySet, Sum, Q
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException, PermissionDenied
from ..models import Contract, ContractPayment, ContractFinanceLog, InvoiceStatus, LogLevel


class ContractPaymentService:
    """
    合同收款服务
    
    职责：
    - 收款记录的 CRUD 操作
    - 金额校验（累计收款不超过合同固定金额）
    - 发票状态自动计算
    - 权限检查（管理员权限）
    - 财务日志记录
    """

    def __init__(self):
        """构造函数，预留依赖注入扩展"""
        pass

    def list_payments(
        self,
        contract_id: Optional[int] = None,
        invoice_status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        user=None,
        perm_open_access: bool = False,
    ) -> QuerySet:
        """
        获取收款列表
        
        Args:
            contract_id: 合同 ID（可选）
            invoice_status: 开票状态筛选（可选）
            start_date: 开始日期筛选（可选）
            end_date: 结束日期筛选（可选）
            user: 当前用户
            perm_open_access: 是否开放访问权限
            
        Returns:
            收款记录查询集
        """
        qs = ContractPayment.objects.all().select_related("contract").order_by("-id")
        
        # 构建筛选条件
        filters = Q()
        if contract_id:
            filters &= Q(contract_id=contract_id)
        if invoice_status:
            filters &= Q(invoice_status=invoice_status)
        if start_date:
            filters &= Q(received_at__gte=start_date)
        if end_date:
            filters &= Q(received_at__lte=end_date)
        
        if filters:
            qs = qs.filter(filters)
        
        return qs

    def get_payment(
        self,
        payment_id: int,
        user=None,
        perm_open_access: bool = False,
    ) -> ContractPayment:
        """
        获取单个收款记录
        
        Args:
            payment_id: 收款 ID
            user: 当前用户
            perm_open_access: 是否开放访问权限
            
        Returns:
            收款对象
            
        Raises:
            NotFoundError: 收款不存在
        """
        try:
            return ContractPayment.objects.select_related("contract").get(id=payment_id)
        except ContractPayment.DoesNotExist:
            raise NotFoundError(f"收款记录 {payment_id} 不存在")

    @transaction.atomic
    def create_payment(
        self,
        contract_id: int,
        amount: Decimal,
        received_at: Optional[date] = None,
        invoice_status: Optional[str] = None,
        invoiced_amount: Optional[Decimal] = None,
        note: Optional[str] = None,
        user=None,
        confirm: bool = False,
    ) -> ContractPayment:
        """
        创建收款记录
        
        Args:
            contract_id: 合同 ID
            amount: 收款金额
            received_at: 收款日期
            invoice_status: 开票状态
            invoiced_amount: 已开票金额
            note: 备注
            user: 当前用户
            confirm: 是否二次确认
            
        Returns:
            创建的收款对象
            
        Raises:
            PermissionDenied: 无管理员权限
            ValidationException: 数据验证失败
            NotFoundError: 合同不存在
        """
        # 权限检查
        self._require_admin(user)
        
        # 二次确认检查
        if not confirm:
            raise ValidationException("关键操作需二次确认")
        
        # 获取合同
        contract = self._get_contract(contract_id)
        
        # 金额校验
        amount_float = float(amount)
        if amount_float <= 0:
            raise ValidationException("收款金额需大于0")
        
        # 合规性校验：累计收款不超过合同固定金额
        total_received = self._get_total_received(contract_id)
        if contract.fixed_amount is not None:
            if amount_float + float(total_received) - float(contract.fixed_amount) > 1e-6:
                self._log_finance(
                    contract.id,
                    self._get_user_id(user),
                    "create_payment_over_fixed",
                    "WARN",
                    {
                        "amount": amount_float,
                        "total_received": float(total_received),
                        "fixed_amount": float(contract.fixed_amount),
                    },
                )
                raise ValidationException("累计收款超过合同固定金额")
        
        # 发票校验和状态计算
        invoiced_amount_float = float(invoiced_amount or 0)
        if invoiced_amount_float < 0 or invoiced_amount_float - amount_float > 1e-6:
            raise ValidationException("开票金额不能大于收款金额")
        
        inv_status = self._calculate_invoice_status(
            invoiced_amount_float, amount_float, invoice_status
        )
        
        # 创建收款记录
        obj = ContractPayment.objects.create(
            contract=contract,
            amount=amount_float,
            received_at=received_at or timezone.localdate(),
            invoice_status=inv_status,
            invoiced_amount=invoiced_amount_float,
            note=note,
        )
        
        # 记录财务日志
        self._log_finance(
            contract.id,
            self._get_user_id(user),
            "create_payment",
            "INFO",
            {"payment_id": obj.id, "amount": amount_float},
        )
        
        return obj

    @transaction.atomic
    def update_payment(
        self,
        payment_id: int,
        data: Dict[str, Any],
        user=None,
        confirm: bool = False,
    ) -> ContractPayment:
        """
        更新收款记录
        
        Args:
            payment_id: 收款 ID
            data: 更新数据
            user: 当前用户
            confirm: 是否二次确认
            
        Returns:
            更新后的收款对象
            
        Raises:
            PermissionDenied: 无管理员权限
            ValidationException: 数据验证失败
            NotFoundError: 收款不存在
        """
        # 权限检查
        self._require_admin(user)
        
        # 二次确认检查
        if not confirm:
            raise ValidationException("关键操作需二次确认")
        
        # 获取收款记录
        obj = self.get_payment(payment_id)
        
        # 记录旧值
        old = {
            "amount": float(obj.amount),
            "received_at": str(obj.received_at),
            "invoice_status": obj.invoice_status,
            "invoiced_amount": float(obj.invoiced_amount),
            "note": obj.note,
        }
        
        # 更新金额
        if "amount" in data:
            amount = float(data["amount"])
            if amount <= 0:
                raise ValidationException("收款金额需大于0")
            
            # 合规校验：替换后累计不超过固定金额
            total_except = self._get_total_received(obj.contract_id, exclude_id=obj.id)
            contract = obj.contract
            if contract.fixed_amount is not None:
                if amount + float(total_except) - float(contract.fixed_amount) > 1e-6:
                    self._log_finance(
                        contract.id,
                        self._get_user_id(user),
                        "update_payment_over_fixed",
                        "WARN",
                        {
                            "amount": amount,
                            "total_except": float(total_except),
                            "fixed_amount": float(contract.fixed_amount),
                        },
                    )
                    raise ValidationException("累计收款超过合同固定金额")
            obj.amount = amount
        
        # 更新收款日期
        if "received_at" in data and data["received_at"]:
            obj.received_at = data["received_at"]
        
        # 更新发票信息
        if "invoiced_amount" in data or "invoice_status" in data:
            invoiced_amount = float(data.get("invoiced_amount", obj.invoiced_amount))
            if invoiced_amount < 0 or invoiced_amount - float(obj.amount) > 1e-6:
                raise ValidationException("开票金额不能大于收款金额")
            
            inv_status = self._calculate_invoice_status(
                invoiced_amount,
                float(obj.amount),
                data.get("invoice_status", obj.invoice_status),
            )
            obj.invoiced_amount = invoiced_amount
            obj.invoice_status = inv_status
        
        # 更新备注
        if "note" in data:
            obj.note = data["note"]
        
        obj.save()
        
        # 记录财务日志
        self._log_finance(
            obj.contract_id,
            self._get_user_id(user),
            "update_payment",
            "INFO",
            {"payment_id": obj.id, "old": old},
        )
        
        return obj

    @transaction.atomic
    def delete_payment(
        self,
        payment_id: int,
        user=None,
        confirm: bool = False,
    ) -> Dict[str, bool]:
        """
        删除收款记录
        
        Args:
            payment_id: 收款 ID
            user: 当前用户
            confirm: 是否二次确认
            
        Returns:
            {"success": True}
            
        Raises:
            PermissionDenied: 无管理员权限
            ValidationException: 未二次确认
            NotFoundError: 收款不存在
        """
        # 权限检查
        self._require_admin(user)
        
        # 二次确认检查
        if not confirm:
            raise ValidationException("关键操作需二次确认")
        
        # 获取收款记录
        obj = self.get_payment(payment_id)
        cid = obj.contract_id
        pid = obj.id
        
        obj.delete()
        
        # 记录财务日志
        self._log_finance(
            cid,
            self._get_user_id(user),
            "delete_payment",
            "INFO",
            {"payment_id": pid},
        )
        
        return {"success": True}

    # ==================== 内部方法 ====================

    def _require_admin(self, user) -> None:
        """
        检查管理员权限
        
        Args:
            user: 当前用户
            
        Raises:
            PermissionDenied: 无管理员权限
        """
        if not (
            getattr(user, "is_authenticated", False)
            and getattr(user, "is_admin", False)
        ):
            raise PermissionDenied("无权限")

    def _get_contract(self, contract_id: int) -> Contract:
        """
        获取合同
        
        Args:
            contract_id: 合同 ID
            
        Returns:
            合同对象
            
        Raises:
            NotFoundError: 合同不存在
        """
        try:
            return Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(f"合同 {contract_id} 不存在")

    def _get_total_received(
        self, contract_id: int, exclude_id: Optional[int] = None
    ) -> Decimal:
        """
        获取合同累计收款金额
        
        Args:
            contract_id: 合同 ID
            exclude_id: 排除的收款 ID（用于更新时计算）
            
        Returns:
            累计收款金额
        """
        qs = ContractPayment.objects.filter(contract_id=contract_id)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        result = qs.aggregate(s=Sum("amount"))["s"]
        return Decimal(str(result)) if result else Decimal("0")

    def _calculate_invoice_status(
        self,
        invoiced_amount: float,
        amount: float,
        current_status: Optional[str] = None,
    ) -> str:
        """
        计算发票状态
        
        Args:
            invoiced_amount: 已开票金额
            amount: 收款金额
            current_status: 当前状态
            
        Returns:
            计算后的发票状态
        """
        if invoiced_amount == 0:
            return InvoiceStatus.UNINVOICED
        elif 0 < invoiced_amount < amount:
            return InvoiceStatus.INVOICED_PARTIAL
        else:
            return InvoiceStatus.INVOICED_FULL

    def _get_user_id(self, user) -> Optional[int]:
        """
        获取用户 ID
        
        Args:
            user: 用户对象
            
        Returns:
            用户 ID 或 None
        """
        return getattr(user, "id", None)

    def _log_finance(
        self,
        contract_id: int,
        actor_id: Optional[int],
        action: str,
        level: str = "INFO",
        payload: Optional[Dict] = None,
    ) -> None:
        """
        记录财务日志
        
        Args:
            contract_id: 合同 ID
            actor_id: 操作人 ID
            action: 操作类型
            level: 日志级别
            payload: 操作数据
        """
        if actor_id is None:
            return
        try:
            ContractFinanceLog.objects.create(
                contract_id=contract_id,
                action=action,
                level=level,
                actor_id=actor_id,
                payload=payload or {},
            )
        except Exception:
            # 日志记录失败不影响主流程
            pass
