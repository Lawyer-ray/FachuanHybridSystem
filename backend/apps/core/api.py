"""
Core App API
提供系统配置和业务配置的 API 端点
"""
from typing import List, Optional
from ninja import Router, Schema

from . import business_config
from .business_config import CaseTypeCode

router = Router()


class StageItem(Schema):
    """阶段配置项"""
    value: str
    label: str


class LegalStatusItem(Schema):
    """诉讼地位配置项"""
    value: str
    label: str


class CaseTypeItem(Schema):
    """案件类型配置项"""
    value: str
    label: str


class BusinessConfigOut(Schema):
    """业务配置输出"""
    case_types: List[CaseTypeItem]
    stages: List[StageItem]
    legal_statuses: List[LegalStatusItem]


@router.get("/business", response=BusinessConfigOut)
def get_business_config(request, case_type: Optional[str] = None):
    """
    获取业务配置

    Args:
        case_type: 案件类型代码，用于过滤适用的阶段和诉讼地位

    Returns:
        业务配置，包含案件类型、阶段、诉讼地位列表
    """
    # 案件类型列表（固定）
    case_types = [
        CaseTypeItem(value=CaseTypeCode.CIVIL, label="民商事"),
        CaseTypeItem(value=CaseTypeCode.CRIMINAL, label="刑事"),
        CaseTypeItem(value=CaseTypeCode.ADMINISTRATIVE, label="行政"),
        CaseTypeItem(value=CaseTypeCode.LABOR, label="劳动仲裁"),
        CaseTypeItem(value=CaseTypeCode.INTL, label="商事仲裁"),
        CaseTypeItem(value=CaseTypeCode.SPECIAL, label="专项服务"),
        CaseTypeItem(value=CaseTypeCode.ADVISOR, label="常法顾问"),
    ]

    # 根据案件类型获取可用的阶段
    stages = [
        StageItem(value=v, label=l)
        for v, l in business_config.get_stages_for_case_type(case_type)
    ]

    # 根据案件类型获取可用的诉讼地位
    legal_statuses = [
        LegalStatusItem(value=v, label=l)
        for v, l in business_config.get_legal_statuses_for_case_type(case_type)
    ]

    return BusinessConfigOut(
        case_types=case_types,
        stages=stages,
        legal_statuses=legal_statuses,
    )


@router.get("/stages", response=List[StageItem])
def get_stages(request, case_type: Optional[str] = None):
    """
    获取案件阶段列表

    Args:
        case_type: 案件类型代码，用于过滤
    """
    return [
        StageItem(value=v, label=l)
        for v, l in business_config.get_stages_for_case_type(case_type)
    ]


@router.get("/legal-statuses", response=List[LegalStatusItem])
def get_legal_statuses(request, case_type: Optional[str] = None):
    """
    获取诉讼地位列表

    Args:
        case_type: 案件类型代码，用于过滤
    """
    return [
        LegalStatusItem(value=v, label=l)
        for v, l in business_config.get_legal_statuses_for_case_type(case_type)
    ]
