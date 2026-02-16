"""
Litigation AI 单元测试配置
"""
import pytest
from unittest.mock import Mock


@pytest.fixture(autouse=True)
def setup_service_locator():
    """自动设置 ServiceLocator，确保测试中的服务正确初始化"""
    from apps.core.interfaces import ServiceLocator
    
    # 确保 ServiceLocator 已初始化
    # 在测试环境中，ServiceLocator 会自动使用真实的服务实现
    yield
    
    # 测试后清理（如果需要）
    pass


@pytest.fixture
def test_lawyer(db):
    """创建测试律师"""
    from apps.organization.models import Lawyer
    return Lawyer.objects.create(username="test_lawyer", real_name="测试律师")


@pytest.fixture
def test_case(db):
    """创建测试案件"""
    from apps.cases.models import Case
    return Case.objects.create(name="测试案件", contract=None)
