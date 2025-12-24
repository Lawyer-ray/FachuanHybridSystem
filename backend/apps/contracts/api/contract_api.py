from typing import List, Optional
from ninja import Router
from ..schemas import ContractIn, ContractOut, ContractUpdate, ContractPaymentIn, UpdateLawyersIn, ContractPartySourceOut
from ..services.contract_service import ContractService
import logging

logger = logging.getLogger("apps.contracts.api")
router = Router()


def _get_contract_service() -> ContractService:
    """
    工厂函数：创建 ContractService 实例并注入依赖

    通过注入依赖，实现合同服务与其他模块的解耦：
    - CaseServiceAdapter: 案件服务适配器
    - ContractPaymentService: 收款服务
    - SupplementaryAgreementService: 补充协议服务

    Returns:
        配置好依赖的 ContractService 实例
    
    Requirements: 1.5
    """
    from apps.cases.services import CaseServiceAdapter
    from apps.client.services import ClientServiceAdapter
    from ..services.contract_payment_service import ContractPaymentService
    from ..services.supplementary_agreement_service import SupplementaryAgreementService
    
    case_service = CaseServiceAdapter()
    payment_service = ContractPaymentService()
    supplementary_agreement_service = SupplementaryAgreementService(
        client_service=ClientServiceAdapter()
    )
    
    return ContractService(
        case_service=case_service,
        payment_service=payment_service,
        supplementary_agreement_service=supplementary_agreement_service,
    )


@router.get("/contracts", response=List[ContractOut])
def list_contracts(request, case_type: Optional[str] = None, status: Optional[str] = None):
    """
    获取合同列表
    
    Requirements: 6.1, 6.2, 6.3
    """
    # 使用工厂函数创建 Service 实例
    service = _get_contract_service()
    
    # 调用 Service 层方法（包含权限过滤）
    return service.list_contracts(
        case_type=case_type,
        status=status,
        user=getattr(request, "user", None),
        org_access=getattr(request, "org_access", None),
        perm_open_access=getattr(request, "perm_open_access", False),
    )


@router.get("/contracts/{contract_id}", response=ContractOut)
def get_contract(request, contract_id: int):
    """
    获取合同详情
    
    Requirements: 6.1, 6.2, 6.3
    """
    # 使用工厂函数创建 Service 实例
    service = _get_contract_service()
    
    # 调用 Service 层方法（包含权限检查）
    return service.get_contract(
        contract_id=contract_id,
        user=getattr(request, "user", None),
        org_access=getattr(request, "org_access", None),
        perm_open_access=getattr(request, "perm_open_access", False),
    )


class ContractWithCasesIn(ContractIn):
    cases: Optional[list[dict]] = None


@router.post("/contracts/full", response=ContractOut)
def create_contract_with_cases(request, payload: ContractWithCasesIn):
    """
    创建合同并关联案件

    API 层职责：
    1. 接收请求参数
    2. 调用 Service 层方法
    3. 返回响应
    
    Requirements: 4.1, 4.2, 4.3
    """
    # 使用工厂函数创建 Service 实例（注入 CaseServiceAdapter 依赖）
    service = _get_contract_service()

    # 提取数据
    data = payload.dict()
    cases_data = data.pop("cases", None)
    lawyer_ids = data.pop("lawyer_ids", [])  # 从 payload 中提取 lawyer_ids

    # 调用 Service 层方法
    contract = service.create_contract_with_cases(
        contract_data=data,
        cases_data=cases_data,
        assigned_lawyer_ids=lawyer_ids  # 使用 lawyer_ids
    )

    return contract


@router.put("/contracts/{contract_id}", response=ContractOut)
def update_contract(
    request,
    contract_id: int,
    payload: ContractUpdate,
    sync_cases: Optional[bool] = False,
    confirm_finance: Optional[bool] = False,
    new_payments: Optional[list[ContractPaymentIn]] = None
):
    """
    更新合同

    API 层职责：
    1. 接收请求参数
    2. 调用 Service 层方法
    3. 返回响应
    
    所有业务验证（财务确认、权限检查）在 Service 层处理
    
    Requirements: 1.1, 1.2, 1.3, 4.3
    """
    # 使用工厂函数创建 Service 实例
    service = _get_contract_service()

    # 提取更新数据
    data = payload.dict(exclude_unset=True)

    # 获取用户信息
    user = getattr(request, "user", None)

    # 所有参数直接传递给 Service，验证逻辑在 Service 层
    contract = service.update_contract_with_finance(
        contract_id=contract_id,
        update_data=data,
        user=user,
        confirm_finance=confirm_finance,
        new_payments=[p.dict() for p in new_payments] if new_payments else None,
    )

    return contract


@router.post("/contracts", response=ContractOut)
def create_contract(
    request,
    payload: ContractIn,
    payments: Optional[list[ContractPaymentIn]] = None,
    confirm_finance: Optional[bool] = False
):
    """
    创建合同

    API 层职责：
    1. 接收请求参数
    2. 调用 Service 层方法
    3. 返回响应
    
    所有业务验证（财务确认）在 Service 层处理
    
    Requirements: 1.1, 5.1, 5.3
    """
    # 使用工厂函数创建 Service 实例
    service = _get_contract_service()

    # 提取数据
    data = payload.dict()
    lawyer_ids = data.pop("lawyer_ids", [])  # 从 payload 中提取 lawyer_ids

    # 获取用户信息
    user = getattr(request, "user", None)

    # 所有参数直接传递给 Service，验证逻辑在 Service 层
    contract = service.create_contract_with_cases(
        contract_data=data,
        cases_data=None,
        assigned_lawyer_ids=lawyer_ids,
        payments_data=[p.dict() for p in payments] if payments else None,
        confirm_finance=confirm_finance,
        user=user,
    )

    return contract


@router.put("/contracts/{contract_id}/lawyers", response=ContractOut)
def update_contract_lawyers(request, contract_id: int, payload: UpdateLawyersIn):
    """
    更新合同律师指派
    
    API 层职责：
    1. 接收请求参数
    2. 调用 Service 层方法
    3. 返回响应
    
    Requirements: 5.1, 5.2, 5.3
    """
    # 使用工厂函数创建 Service 实例
    service = _get_contract_service()
    
    # 调用 Service 层更新律师指派
    contract = service.update_contract_lawyers(
        contract_id=contract_id,
        lawyer_ids=payload.lawyer_ids
    )
    return contract


@router.delete("/contracts/{contract_id}")
def delete_contract(request, contract_id: int):
    """
    删除合同

    API 层职责：
    1. 接收请求参数
    2. 调用 Service 层方法
    3. 返回响应
    """
    # 使用工厂函数创建 Service 实例
    service = _get_contract_service()

    service.delete_contract(contract_id)
    return {"success": True}


@router.get("/contracts/{contract_id}/all-parties", response=List[ContractPartySourceOut])
def get_contract_all_parties(request, contract_id: int):
    """
    获取合同及补充协议的所有当事人
    
    返回合同当事人和补充协议当事人的聚合列表，按 client_id 去重。
    每个当事人包含 id、name、source 字段，source 标识来源：
    - "contract": 来自合同当事人
    - "supplementary": 来自补充协议当事人
    
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    service = _get_contract_service()
    
    # 调用 Service 层方法获取所有当事人
    # NotFoundError 会被框架自动处理为 404 响应
    parties = service.get_all_parties(contract_id)
    
    return parties
