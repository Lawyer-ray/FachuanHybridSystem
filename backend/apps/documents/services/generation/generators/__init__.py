"""
具体生成器实现模块

包含各种文书类型的具体生成器实现.
模块加载时会自动发现并注册所有生成器.
"""

# 导入具体生成器(触发注册)
from .contract_generator import ContractGenerator

__all__ = [
    "ContractGenerator",
]
