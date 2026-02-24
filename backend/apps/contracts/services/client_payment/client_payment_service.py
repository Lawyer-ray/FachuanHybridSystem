"""客户回款记录服务层"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import QuerySet, Sum
from django.utils.translation import gettext as _

from apps.contracts.models import ClientPaymentRecord, Contract
from apps.core.exceptions import NotFoundError, ValidationException

logger = logging.getLogger("apps.contracts")


class ClientPaymentRecordService:
    """
    客户回款记录服务

    职责:
    - 回款记录的 CRUD 操作
    - 金额校验
    - 案件归属验证
    """

    def __init__(self) -> None:
        """构造函数"""

    @transaction.atomic
    def create_payment_record(
        self,
        contract_id: int,
        amount: Decimal,
        case_ids: list[int] | None = None,
        note: str = "",
    ) -> ClientPaymentRecord:
        """
        创建客户回款记录

        Args:
            contract_id: 合同 ID
            amount: 回款金额
            case_ids: 关联案件 ID 列表
            note: 备注

        Returns:
            创建的回款记录

        Raises:
            NotFoundError: 合同不存在
            ValidationException: 数据验证失败
        """
        # 验证合同存在
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(_("合同 %(id)s 不存在") % {"id": contract_id}) from None

        # 验证金额
        if amount <= 0:
            raise ValidationException(_("回款金额必须大于零"))

        if amount > Decimal("999999999999.99"):
            raise ValidationException(_("回款金额不能超过 14 位数字（含 2 位小数）"))

        # 验证案件归属
        if case_ids:
            if not self.validate_cases_belong_to_contract(contract_id, case_ids):
                raise ValidationException(_("所选案件不属于该合同"))

        # 创建回款记录
        record = ClientPaymentRecord.objects.create(
            contract=contract,
            amount=amount,
            note=note,
        )

        # 关联案件
        if case_ids:
            record.cases.set(case_ids)

        logger.info(
            "创建客户回款记录: contract_id=%s, amount=%s, record_id=%s",
            contract_id,
            amount,
            record.id,
        )

        return record

    @transaction.atomic
    def update_payment_record(
        self,
        record_id: int,
        amount: Decimal | None = None,
        case_ids: list[int] | None = None,
        note: str | None = None,
    ) -> ClientPaymentRecord:
        """
        更新客户回款记录

        Args:
            record_id: 回款记录 ID
            amount: 回款金额
            case_ids: 关联案件 ID 列表
            note: 备注

        Returns:
            更新后的回款记录

        Raises:
            NotFoundError: 记录不存在
            ValidationException: 数据验证失败
        """
        # 获取记录
        try:
            record = ClientPaymentRecord.objects.get(id=record_id)
        except ClientPaymentRecord.DoesNotExist:
            raise NotFoundError(_("客户回款记录 %(id)s 不存在") % {"id": record_id}) from None

        # 更新金额
        if amount is not None:
            if amount <= 0:
                raise ValidationException(_("回款金额必须大于零"))

            if amount > Decimal("999999999999.99"):
                raise ValidationException(_("回款金额不能超过 14 位数字（含 2 位小数）"))

            record.amount = amount

        # 更新案件关联
        if case_ids is not None:
            if case_ids and not self.validate_cases_belong_to_contract(record.contract_id, case_ids):
                raise ValidationException(_("所选案件不属于该合同"))
            record.cases.set(case_ids)

        # 更新备注
        if note is not None:
            record.note = note

        record.save()

        logger.info("更新客户回款记录: record_id=%s", record_id)

        return record

    @transaction.atomic
    def delete_payment_record(self, record_id: int) -> None:
        """
        删除客户回款记录

        Args:
            record_id: 回款记录 ID

        Raises:
            NotFoundError: 记录不存在
        """
        try:
            record = ClientPaymentRecord.objects.get(id=record_id)
        except ClientPaymentRecord.DoesNotExist:
            raise NotFoundError(_("客户回款记录 %(id)s 不存在") % {"id": record_id}) from None

        # 删除关联图片
        if record.image_path:
            from .client_payment_image_service import ClientPaymentImageService

            image_service = ClientPaymentImageService()
            image_service.delete_image(record.image_path)

        record.delete()

        logger.info("删除客户回款记录: record_id=%s", record_id)

    def get_contract_payment_records(self, contract_id: int) -> QuerySet[ClientPaymentRecord, ClientPaymentRecord]:
        """
        获取合同的所有回款记录

        Args:
            contract_id: 合同 ID

        Returns:
            回款记录查询集
        """
        return ClientPaymentRecord.objects.filter(contract_id=contract_id).prefetch_related("cases").order_by("-created_at")

    def calculate_total_amount(self, contract_id: int) -> Decimal:
        """
        计算合同的回款总额

        Args:
            contract_id: 合同 ID

        Returns:
            回款总额
        """
        result = ClientPaymentRecord.objects.filter(contract_id=contract_id).aggregate(total=Sum("amount"))["total"]
        return result if result is not None else Decimal("0")

    def validate_cases_belong_to_contract(self, contract_id: int, case_ids: list[int]) -> bool:
        """
        验证案件是否属于指定合同

        Args:
            contract_id: 合同 ID
            case_ids: 案件 ID 列表

        Returns:
            是否全部属于该合同
        """
        from apps.cases.models import Case

        # 查询这些案件中属于该合同的数量
        valid_count = Case.objects.filter(id__in=case_ids, contract_id=contract_id).count()

        # 如果数量匹配，说明所有案件都属于该合同
        return valid_count == len(case_ids)
