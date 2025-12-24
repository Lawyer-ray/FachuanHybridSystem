"""
Pytest 配置文件
提供测试 fixtures
"""
import os
import sys
import django
import pytest

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'apiSystem'))

# 设置 Django 配置
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """
    设置测试数据库
    
    确保测试使用独立的测试数据库，不影响生产数据库
    """
    with django_db_blocker.unblock():
        # pytest-django 会自动创建测试数据库
        # 这里只需要确保使用正确的数据库配置
        from django.conf import settings
        
        # 验证使用的是测试数据库
        db_name = str(settings.DATABASES['default']['NAME'])
        
        # 检查是否是测试数据库（支持多种格式）
        is_test_db = (
            'test_' in db_name or
            ':memory:' in db_name or
            'memorydb' in db_name or  # Django 测试数据库格式
            db_name == ':memory:'
        )
        
        assert is_test_db, \
            f"错误：测试正在使用生产数据库 {db_name}！测试已中止。"
        
        yield
        
        # 测试结束后，pytest-django 会自动清理测试数据库


@pytest.fixture(scope='session')
def django_db_modify_db_settings():
    """
    修改测试数据库设置
    
    优化测试数据库性能
    """
    from django.conf import settings
    
    # 使用内存数据库加速测试
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'ATOMIC_REQUESTS': False,
        'CONN_MAX_AGE': 0,
        'TIME_ZONE': 'Asia/Shanghai',  # 添加TIME_ZONE设置
        'OPTIONS': {
            'timeout': 20,
        }
    }


@pytest.fixture
def api_client():
    """提供 API 测试客户端"""
    from django.test import Client
    return Client()


@pytest.fixture
def authenticated_client(db):
    """提供已认证的测试客户端"""
    from django.test import Client
    from apps.organization.models import LawFirm, Lawyer
    
    client = Client()
    firm = LawFirm.objects.create(name="测试律所")
    user = Lawyer.objects.create_user(
        username="testuser",
        password="testpass123",
        is_admin=True,
        law_firm=firm,
    )
    client.force_login(user)
    return client


@pytest.fixture
def law_firm(db):
    """提供测试律所"""
    from apps.organization.models import LawFirm
    return LawFirm.objects.create(name="Fixture测试律所")


@pytest.fixture
def lawyer(db, law_firm):
    """提供测试律师"""
    from apps.organization.models import Lawyer
    return Lawyer.objects.create_user(
        username="fixturelawyer",
        password="testpass123",
        real_name="Fixture律师",
        law_firm=law_firm,
    )


@pytest.fixture
def admin_lawyer(db, law_firm):
    """提供管理员律师"""
    from apps.organization.models import Lawyer
    return Lawyer.objects.create_user(
        username="adminlawyer",
        password="testpass123",
        is_admin=True,
        law_firm=law_firm,
    )


@pytest.fixture
def client_entity(db):
    """提供测试客户"""
    from apps.client.models import Client
    return Client.objects.create(
        name="Fixture测试客户",
        client_type=Client.NATURAL,
        is_our_client=True,
    )


@pytest.fixture
def contract(db, lawyer):
    """提供测试合同"""
    from apps.contracts.models import Contract
    return Contract.objects.create(
        name="Fixture测试合同",
        case_type="civil",
        assigned_lawyer=lawyer,
    )


@pytest.fixture
def case(db, contract):
    """提供测试案件"""
    from apps.cases.models import Case
    return Case.objects.create(
        name="Fixture测试案件",
        contract=contract,
    )


# ========== Hypothesis 配置 ==========

from hypothesis import settings, Verbosity

# 配置 Hypothesis
settings.register_profile("default", max_examples=100, verbosity=Verbosity.normal)
settings.register_profile("ci", max_examples=1000, verbosity=Verbosity.verbose)
settings.register_profile("dev", max_examples=10, verbosity=Verbosity.verbose)
settings.register_profile("debug", max_examples=10, verbosity=Verbosity.debug)

# 加载配置（默认使用 default）
import os
profile = os.getenv('HYPOTHESIS_PROFILE', 'default')
settings.load_profile(profile)


# ========== 测试工具 Fixtures ==========

@pytest.fixture
def mock_contract_service():
    """提供 Mock 合同服务"""
    from tests.mocks import MockContractService
    return MockContractService()


@pytest.fixture
def mock_case_service():
    """提供 Mock 案件服务"""
    from tests.mocks import MockCaseService
    return MockCaseService()


@pytest.fixture
def mock_permission_service():
    """提供 Mock 权限服务"""
    from tests.mocks import MockPermissionService
    return MockPermissionService()


@pytest.fixture
def mock_email_service():
    """提供 Mock 邮件服务"""
    from tests.mocks import MockEmailService
    return MockEmailService()


@pytest.fixture
def query_counter(db):
    """
    查询计数器
    
    用于测试数据库查询优化，检测 N+1 查询问题
    
    使用方法：
        with query_counter() as counter:
            # 执行操作
            cases = Case.objects.select_related('contract').all()
            list(cases)
        
        assert counter.count <= 1  # 断言查询次数
    """
    from django.test.utils import CaptureQueriesContext
    from django.db import connection
    
    class QueryCounter:
        def __init__(self):
            self.context = None
            self.count = 0
        
        def __enter__(self):
            self.context = CaptureQueriesContext(connection)
            self.context.__enter__()
            return self
        
        def __exit__(self, *args):
            self.context.__exit__(*args)
            self.count = len(self.context.captured_queries)
        
        @property
        def queries(self):
            """获取所有查询"""
            return self.context.captured_queries if self.context else []
    
    def _counter():
        return QueryCounter()
    
    return _counter


@pytest.fixture
def assert_num_queries(db):
    """
    断言查询次数
    
    使用方法：
        with assert_num_queries(1):
            # 执行操作，应该只有 1 次查询
            cases = Case.objects.select_related('contract').all()
            list(cases)
    """
    from django.test.utils import CaptureQueriesContext
    from django.db import connection
    
    class AssertNumQueries:
        def __init__(self, expected_count):
            self.expected_count = expected_count
            self.context = None
        
        def __enter__(self):
            self.context = CaptureQueriesContext(connection)
            self.context.__enter__()
            return self
        
        def __exit__(self, *args):
            self.context.__exit__(*args)
            actual_count = len(self.context.captured_queries)
            
            if actual_count != self.expected_count:
                queries = '\n'.join(
                    f"{i+1}. {q['sql']}"
                    for i, q in enumerate(self.context.captured_queries)
                )
                raise AssertionError(
                    f"Expected {self.expected_count} queries, but got {actual_count}:\n{queries}"
                )
    
    return AssertNumQueries
