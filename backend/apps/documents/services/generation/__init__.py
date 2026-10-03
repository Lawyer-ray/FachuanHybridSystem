"""
文书生成器模块

提供文书生成的核心功能,包括:
- ContextBuilder: 上下文构建器
- ContractGenerationService: 合同生成服务
- FolderGenerationService: 文件夹生成服务
- SupplementaryAgreementGenerationService: 补充协议生成服务
- PreservationMaterialsGenerationService: 财产保全材料生成服务
- GenerationResult: 生成结果数据类
- PartyInfo, ComplaintOutput, DefenseOutput: Pydantic 输出模型
"""

from .context_builder import ContextBuilder
from .contract_generation_service import ContractGenerationService
from .folder_generation_service import FolderGenerationService
from .litigation_generation_service import LitigationGenerationService
from .outputs import ComplaintOutput, DefenseOutput, PartyInfo
from .preservation_materials_generation_service import PreservationMaterialsGenerationService
from .result import GenerationResult
from .supplementary_agreement_generation_service import SupplementaryAgreementGenerationService

__all__ = [
    "ComplaintOutput",
    "ContextBuilder",
    "ContractGenerationService",
    "DefenseOutput",
    "FolderGenerationService",
    "GenerationResult",
    "LitigationGenerationService",
    "PartyInfo",
    "PreservationMaterialsGenerationService",
    "SupplementaryAgreementGenerationService",
]
