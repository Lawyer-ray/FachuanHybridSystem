"""
业务配置模块
将硬编码的业务逻辑配置化，支持动态调整
"""
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


@dataclass
class StageConfig:
    """阶段配置"""
    value: str
    label: str
    applicable_case_types: List[str] = field(default_factory=list)  # 空列表表示适用所有类型


@dataclass
class LegalStatusConfig:
    """诉讼地位配置"""
    value: str
    label: str
    applicable_case_types: List[str] = field(default_factory=list)


class CaseTypeCode:
    """案件类型代码"""
    CIVIL = "civil"
    CRIMINAL = "criminal"
    ADMINISTRATIVE = "administrative"
    LABOR = "labor"
    INTL = "intl"
    SPECIAL = "special"
    ADVISOR = "advisor"


# 案件阶段配置
CASE_STAGES: List[StageConfig] = [
    # 通用阶段
    StageConfig("first_trial", "一审", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),
    StageConfig("second_trial", "二审", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),
    StageConfig("enforcement", "执行", [CaseTypeCode.CIVIL, CaseTypeCode.ADMINISTRATIVE]),

    # 劳动仲裁
    StageConfig("labor_arbitration", "劳动仲裁", [CaseTypeCode.LABOR]),

    # 行政
    StageConfig("administrative_review", "行政复议", [CaseTypeCode.ADMINISTRATIVE]),

    # 刑事专用
    StageConfig("private_prosecution", "自诉", [CaseTypeCode.CRIMINAL]),
    StageConfig("investigation", "侦查", [CaseTypeCode.CRIMINAL]),
    StageConfig("prosecution_review", "审查起诉", [CaseTypeCode.CRIMINAL]),
    StageConfig("death_penalty_review", "死刑复核程序", [CaseTypeCode.CRIMINAL]),

    # 重审/再审
    StageConfig("retrial_first", "重审一审", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),
    StageConfig("retrial_second", "重审二审", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),
    StageConfig("apply_retrial", "申请再审", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),
    StageConfig("rehearing_first", "再审一审", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),
    StageConfig("rehearing_second", "再审二审", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),
    StageConfig("review", "提审", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),

    # 申诉
    StageConfig("petition", "申诉", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),
    StageConfig("apply_protest", "申请抗诉", [CaseTypeCode.CRIMINAL]),
    StageConfig("petition_protest", "申诉抗诉", [CaseTypeCode.CRIMINAL]),
]


# 诉讼地位配置
LEGAL_STATUSES: List[LegalStatusConfig] = [
    # 民事
    LegalStatusConfig("plaintiff", "原告", [CaseTypeCode.CIVIL]),
    LegalStatusConfig("defendant", "被告", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL]),
    LegalStatusConfig("third", "第三人", [CaseTypeCode.CIVIL, CaseTypeCode.ADMINISTRATIVE]),

    # 仲裁/行政
    LegalStatusConfig("applicant", "申请人", [CaseTypeCode.LABOR, CaseTypeCode.INTL, CaseTypeCode.ADMINISTRATIVE]),
    LegalStatusConfig("respondent", "被申请人", [CaseTypeCode.LABOR, CaseTypeCode.INTL, CaseTypeCode.ADMINISTRATIVE]),

    # 刑事
    LegalStatusConfig("criminal_defendant", "被告人", [CaseTypeCode.CRIMINAL]),
    LegalStatusConfig("victim", "被害人", [CaseTypeCode.CRIMINAL]),

    # 上诉
    LegalStatusConfig("appellant", "上诉人", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),
    LegalStatusConfig("appellee", "被上诉人", [CaseTypeCode.CIVIL, CaseTypeCode.CRIMINAL, CaseTypeCode.ADMINISTRATIVE]),

    # 原审
    LegalStatusConfig("orig_plaintiff", "原审原告", [CaseTypeCode.CIVIL]),
    LegalStatusConfig("orig_defendant", "原审被告", [CaseTypeCode.CIVIL]),
    LegalStatusConfig("orig_third", "原审第三人", [CaseTypeCode.CIVIL, CaseTypeCode.ADMINISTRATIVE]),
]


class BusinessConfig:
    """业务配置管理器"""

    _instance: Optional["BusinessConfig"] = None

    def __new__(cls) -> "BusinessConfig":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_config()
        return cls._instance

    def _init_config(self) -> None:
        """初始化配置"""
        self._stage_map: Dict[str, StageConfig] = {s.value: s for s in CASE_STAGES}
        self._status_map: Dict[str, LegalStatusConfig] = {s.value: s for s in LEGAL_STATUSES}

    def get_stages_for_case_type(self, case_type: Optional[str]) -> List[Tuple[str, str]]:
        """
        获取指定案件类型可用的阶段列表

        Args:
            case_type: 案件类型代码，None 表示返回所有

        Returns:
            [(value, label), ...] 列表
        """
        result = []
        for stage in CASE_STAGES:
            if not stage.applicable_case_types or (case_type and case_type in stage.applicable_case_types):
                result.append((stage.value, stage.label))
        return result

    def get_legal_statuses_for_case_type(self, case_type: Optional[str]) -> List[Tuple[str, str]]:
        """
        获取指定案件类型可用的诉讼地位列表

        Args:
            case_type: 案件类型代码，None 表示返回所有

        Returns:
            [(value, label), ...] 列表
        """
        result = []
        for status in LEGAL_STATUSES:
            if not status.applicable_case_types or (case_type and case_type in status.applicable_case_types):
                result.append((status.value, status.label))
        return result

    def get_stage_label(self, value: str) -> str:
        """获取阶段显示名称"""
        stage = self._stage_map.get(value)
        return stage.label if stage else value

    def get_legal_status_label(self, value: str) -> str:
        """获取诉讼地位显示名称"""
        status = self._status_map.get(value)
        return status.label if status else value

    def is_stage_valid_for_case_type(self, stage: str, case_type: Optional[str]) -> bool:
        """检查阶段是否适用于指定案件类型"""
        config = self._stage_map.get(stage)
        if not config:
            return False
        if not config.applicable_case_types:
            return True
        return case_type in config.applicable_case_types if case_type else True

    def is_legal_status_valid_for_case_type(self, status: str, case_type: Optional[str]) -> bool:
        """检查诉讼地位是否适用于指定案件类型"""
        config = self._status_map.get(status)
        if not config:
            return False
        if not config.applicable_case_types:
            return True
        return case_type in config.applicable_case_types if case_type else True


# 全局配置实例
business_config = BusinessConfig()
