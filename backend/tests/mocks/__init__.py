"""
Mock 服务类

提供用于测试的 Mock 服务基类和常用 Mock 实现
"""
from .base import MockService
from .service_mocks import (
    MockContractService,
    MockCaseService,
    MockPermissionService,
    MockEmailService,
)

__all__ = [
    'MockService',
    'MockContractService',
    'MockCaseService',
    'MockPermissionService',
    'MockEmailService',
]
