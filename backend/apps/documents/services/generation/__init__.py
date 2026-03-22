"""
文书生成器模块

提供文书生成的核心功能,包括:
- BaseGenerator: 生成器基类
- ContextBuilder: 上下文构建器
- ContractGenerationService: 合同生成服务
- FolderGenerationService: 文件夹生成服务
- SupplementaryAgreementGenerationService: 补充协议生成服务
- PreservationMaterialsGenerationService: 财产保全材料生成服务
- GeneratorRegistry: 生成器注册表
- GenerationResult: 生成结果数据类
- PartyInfo, ComplaintOutput, DefenseOutput: Pydantic 输出模型
"""

from .base_generator import BaseGenerator
from .context_builder import ContextBuilder
from .contract_generation_service import ContractGenerationService
from .folder_generation_service import FolderGenerationService
from .litigation_generation_service import LitigationGenerationService
from .outputs import ComplaintOutput, DefenseOutput, PartyInfo
from .preservation_materials_generation_service import PreservationMaterialsGenerationService
from .registry import GeneratorRegistry
from .result import GenerationResult
from .supplementary_agreement_generation_service import SupplementaryAgreementGenerationService

__all__ = [
    "BaseGenerator",
    "ComplaintOutput",
    "ContextBuilder",
    "ContractGenerationService",
    "DefenseOutput",
    "FolderGenerationService",
    "GenerationResult",
    "GeneratorRegistry",
    "LitigationGenerationService",
    "PartyInfo",
    "PreservationMaterialsGenerationService",
    "SupplementaryAgreementGenerationService",
]
