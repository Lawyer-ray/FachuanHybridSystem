"""案件 Admin 服务 - 处理 Admin 层的复杂业务逻辑"""
from typing import Optional
from django.db import transaction

from ..models import (
    Case, CaseParty, CaseAssignment, CaseNumber,
    SupervisingAuthority, CaseLog, CaseLogAttachment
)


class CaseAdminService:
    """案件 Admin 服务"""

    @transaction.atomic
    def duplicate_case(self, case_id: int) -> Case:
        """
        复制案件及其所有关联数据（不复制日志和群聊）
        
        Args:
            case_id: 原案件ID
            
        Returns:
            新创建的案件对象
        """
        # 获取原案件
        original = Case.objects.get(pk=case_id)
        
        # 复制主对象
        new_case = Case.objects.create(
            contract=original.contract,
            is_archived=False,  # 副本默认未建档
            name=f"{original.name} (副本)",
            status=original.status,
            effective_date=original.effective_date,
            cause_of_action=original.cause_of_action,
            target_amount=original.target_amount,
            case_type=original.case_type,
            current_stage=original.current_stage,
        )
        
        # 复制当事人
        for party in original.parties.all():
            CaseParty.objects.create(
                case=new_case,
                client=party.client,
                legal_status=party.legal_status,
            )
        
        # 复制律师指派
        for assignment in original.assignments.all():
            CaseAssignment.objects.create(
                case=new_case,
                lawyer=assignment.lawyer,
            )
        
        # 复制主管机关
        for authority in original.supervising_authorities.all():
            SupervisingAuthority.objects.create(
                case=new_case,
                name=authority.name,
                authority_type=authority.authority_type,
            )
        
        # 复制案号
        for case_number in original.case_numbers.all():
            CaseNumber.objects.create(
                case=new_case,
                number=case_number.number,
                remarks=case_number.remarks,
            )
        
        # 注意：不复制 CaseLog（日志）和 CaseChat（群聊）
        
        return new_case
