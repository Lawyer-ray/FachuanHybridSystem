"""
补充协议 API 层
符合三层架构规范：只做请求/响应处理，业务逻辑在 Service 层
异常处理依赖全局异常处理器，API 层不包含 try/except
"""
from typing import List
from ninja import Router

from ..schemas import (
    SupplementaryAgreementIn,
    SupplementaryAgreementOut,
    SupplementaryAgreementUpdate
)
from ..services.supplementary_agreement_service import SupplementaryAgreementService
from apps.client.services import ClientServiceAdapter

router = Router()


def _get_supplementary_agreement_service() -> SupplementaryAgreementService:
    """工厂函数：创建服务实例并注入依赖"""
    return SupplementaryAgreementService(
        client_service=ClientServiceAdapter()
    )


@router.post("/supplementary-agreements", response=SupplementaryAgreementOut)
def create_supplementary_agreement(request, payload: SupplementaryAgreementIn):
    """
    创建补充协议

    API 层职责：
    1. 接收请求数据
    2. 调用 Service
    3. 返回结果
    
    异常由全局异常处理器处理
    """
    service = _get_supplementary_agreement_service()
    
    return service.create_supplementary_agreement(
        contract_id=payload.contract_id,
        name=payload.name,
        party_ids=payload.party_ids
    )


@router.get("/supplementary-agreements/{agreement_id}", response=SupplementaryAgreementOut)
def get_supplementary_agreement(request, agreement_id: int):
    """
    获取补充协议

    API 层职责：
    1. 接收路径参数
    2. 调用 Service
    3. 返回结果
    
    异常由全局异常处理器处理
    """
    service = _get_supplementary_agreement_service()
    return service.get_supplementary_agreement(agreement_id)


@router.get("/contracts/{contract_id}/supplementary-agreements", response=List[SupplementaryAgreementOut])
def list_supplementary_agreements(request, contract_id: int):
    """
    获取合同的所有补充协议

    API 层职责：
    1. 接收路径参数
    2. 调用 Service
    3. 返回结果列表
    """
    service = _get_supplementary_agreement_service()
    return service.list_by_contract(contract_id)


@router.put("/supplementary-agreements/{agreement_id}", response=SupplementaryAgreementOut)
def update_supplementary_agreement(
    request,
    agreement_id: int,
    payload: SupplementaryAgreementUpdate
):
    """
    更新补充协议

    API 层职责：
    1. 接收参数
    2. 调用 Service
    3. 返回结果
    
    异常由全局异常处理器处理
    """
    service = _get_supplementary_agreement_service()
    
    # 提取更新数据（只包含实际提供的字段）
    data = payload.dict(exclude_unset=True)
    
    return service.update_supplementary_agreement(
        agreement_id=agreement_id,
        name=data.get("name"),
        party_ids=data.get("party_ids")
    )


@router.delete("/supplementary-agreements/{agreement_id}")
def delete_supplementary_agreement(request, agreement_id: int):
    """
    删除补充协议

    API 层职责：
    1. 接收参数
    2. 调用 Service
    3. 返回成功响应
    
    异常由全局异常处理器处理
    """
    service = _get_supplementary_agreement_service()
    service.delete_supplementary_agreement(agreement_id)
    return {"success": True}
