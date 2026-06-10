"""
Pytest 配置文件
提供测试 fixtures
"""

import os
import sys
from typing import Any

import django
import pytest

from apps.core.utils.path import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "apiSystem"))

# 设置 Django 配置
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

# 排除脚本文件（非标准 pytest 测试）
collect_ignore = [
    "tests/unit/automation/test_court_document.py",
]


def _resolve_test_db_engine() -> str:
    """Infer the database engine from environment variables."""
    inferred = "sqlite" if (os.environ.get("DATABASE_PATH") or os.environ.get("TEST_DB_PATH")) else "postgresql"
    return (os.environ.get("TEST_DB_ENGINE") or os.environ.get("DB_ENGINE") or inferred).strip().lower()


def _configure_test_database(django_settings: Any) -> None:
    """Set ``DATABASES['default']`` for the test environment (SQLite or PostgreSQL)."""
    engine = _resolve_test_db_engine()

    if engine in ("sqlite", "sqlite3", "django.db.backends.sqlite3"):
        test_db_path = (os.environ.get("TEST_DB_PATH") or os.environ.get("DATABASE_PATH") or ":memory:").strip()
        django_settings.DATABASES["default"] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": test_db_path,
            "ATOMIC_REQUESTS": False,
            "CONN_MAX_AGE": 0,
            "TIME_ZONE": "Asia/Shanghai",
            "OPTIONS": {"timeout": 20},
        }
        return

    raw_test_password = os.environ.get("TEST_DB_PASSWORD")
    raw_db_password = os.environ.get("DB_PASSWORD")
    resolved_password = (raw_test_password if raw_test_password is not None else raw_db_password) or "postgres"

    django_settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (os.environ.get("TEST_DB_NAME") or "fachuan_test").strip(),
        "USER": (os.environ.get("TEST_DB_USER") or os.environ.get("DB_USER") or "postgres").strip(),
        "PASSWORD": resolved_password.strip(),
        "HOST": (os.environ.get("TEST_DB_HOST") or os.environ.get("DB_HOST") or "127.0.0.1").strip(),
        "PORT": int((os.environ.get("TEST_DB_PORT") or os.environ.get("DB_PORT") or "5432").strip()),
        "ATOMIC_REQUESTS": False,
        "CONN_MAX_AGE": 0,
        "TIME_ZONE": "Asia/Shanghai",
        "CONN_HEALTH_CHECKS": True,
    }


def pytest_configure(config: Any) -> None:
    """
    Apply test database settings once, *before* Django loads settings.

    Sets ``DB_NAME`` env var so that ``apiSystem.settings`` reads the correct
    test database name when it's eventually loaded by ``django.setup()``.
    This avoids the race condition of modifying ``DATABASES`` after settings
    are already cached.
    """
    test_db_name = os.environ.get("TEST_DB_NAME")
    if test_db_name:
        os.environ["DB_NAME"] = test_db_name

    # Production safety check
    db_name = os.environ.get("DB_NAME", "fachuan_dev")
    engine = _resolve_test_db_engine()
    if engine not in ("sqlite", "sqlite3", "django.db.backends.sqlite3"):
        lowered_name = db_name.lower()
        is_test_db = (
            lowered_name.startswith("test_")
            or lowered_name.endswith("_test")
            or "_test_" in lowered_name
            or lowered_name == "test"
            or lowered_name == "fachuan_ci_test"
        )
        if not is_test_db:
            import warnings

            warnings.warn(f"⚠️ 测试正在使用非测试数据库: {db_name}", stacklevel=1)


@pytest.fixture
def api_client() -> Any:
    """提供 API 测试客户端"""
    from django.test import Client

    return Client()


@pytest.fixture
def authenticated_client(db: Any) -> Any:
    """提供已认证的测试客户端"""
    from django.test import Client

    from apps.organization.models import LawFirm, Lawyer

    client = Client()
    firm = LawFirm.objects.create(name="测试律所")
    user = Lawyer.objects.create_user(
        username="testuser",
        password="testpass123",
        is_admin=True,
        is_superuser=True,
        law_firm=firm,
    )
    client.force_login(user)
    return client


@pytest.fixture
def law_firm(db: Any) -> Any:
    """提供测试律所"""
    from apps.organization.models import LawFirm

    return LawFirm.objects.create(name="Fixture测试律所")


@pytest.fixture
def lawyer(db: Any, law_firm: Any) -> Any:
    """提供测试律师"""
    from apps.organization.models import Lawyer

    return Lawyer.objects.create_user(
        username="fixturelawyer",
        password="testpass123",
        real_name="Fixture律师",
        law_firm=law_firm,
    )


@pytest.fixture
def admin_lawyer(db: Any, law_firm: Any) -> Any:
    """提供管理员律师"""
    from apps.organization.models import Lawyer

    return Lawyer.objects.create_user(
        username="adminlawyer",
        password="testpass123",
        is_admin=True,
        law_firm=law_firm,
    )


@pytest.fixture
def client_entity(db: Any) -> Any:
    """提供测试客户"""
    from apps.client.models import Client

    return Client.objects.create(
        name="Fixture测试客户",
        client_type=Client.NATURAL,
        is_our_client=True,
    )


@pytest.fixture
def contract(db: Any, lawyer: Any) -> Any:
    """提供测试合同"""
    from apps.contracts.models import Contract

    return Contract.objects.create(
        name="Fixture测试合同",
        case_type="civil",
    )


@pytest.fixture
def case(db: Any, contract: Any) -> Any:
    """提供测试案件"""
    from apps.cases.models import Case

    return Case.objects.create(
        name="Fixture测试案件",
        contract=contract,
    )


# ========== Hypothesis 配置 ==========

from hypothesis import Verbosity, settings

# 配置 Hypothesis
settings.register_profile("default", max_examples=5, verbosity=Verbosity.normal)
settings.register_profile("ci", max_examples=1000, verbosity=Verbosity.verbose)
settings.register_profile("dev", max_examples=10, verbosity=Verbosity.verbose)
settings.register_profile("debug", max_examples=10, verbosity=Verbosity.debug)

# 加载配置（默认使用 default）
profile = os.getenv("HYPOTHESIS_PROFILE", "default")
settings.load_profile(profile)

# ========== 测试工具 Fixtures ==========


@pytest.fixture
def mock_contract_service() -> Any:
    """提供 Mock 合同服务"""
    from tests.mocks import MockContractService

    return MockContractService()


@pytest.fixture
def mock_case_service() -> Any:
    """提供 Mock 案件服务"""
    from tests.mocks import MockCaseService

    return MockCaseService()


@pytest.fixture
def mock_permission_service() -> Any:
    """提供 Mock 权限服务"""
    from tests.mocks import MockPermissionService

    return MockPermissionService()


@pytest.fixture
def mock_email_service() -> Any:
    """提供 Mock 邮件服务"""
    from tests.mocks import MockEmailService

    return MockEmailService()


@pytest.fixture
def query_counter(db: Any) -> Any:
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
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    class QueryCounter:
        def __init__(self) -> None:
            self.context: CaptureQueriesContext | None = None
            self.count: int = 0

        def __enter__(self) -> "QueryCounter":
            self.context = CaptureQueriesContext(connection)
            self.context.__enter__()
            return self

        def __exit__(self, *args: Any) -> None:
            assert self.context is not None
            self.context.__exit__(*args)
            self.count = len(self.context.captured_queries)

        @property
        def queries(self) -> list[dict[str, Any]]:
            """获取所有查询"""
            return self.context.captured_queries if self.context else []

    def _counter() -> QueryCounter:
        return QueryCounter()

    return _counter


@pytest.fixture
def assert_num_queries(db: Any) -> Any:
    """
    断言查询次数

    使用方法：
        with assert_num_queries(1):
            # 执行操作，应该只有 1 次查询
            cases = Case.objects.select_related('contract').all()
            list(cases)
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    class AssertNumQueries:
        def __init__(self, expected_count: int) -> None:
            self.expected_count = expected_count
            self.context: CaptureQueriesContext | None = None

        def __enter__(self) -> "AssertNumQueries":
            self.context = CaptureQueriesContext(connection)
            self.context.__enter__()
            return self

        def __exit__(self, *args: Any) -> None:
            assert self.context is not None
            self.context.__exit__(*args)
            actual_count = len(self.context.captured_queries)

            if actual_count != self.expected_count:
                queries = "\n".join(f"{i + 1}. {q['sql']}" for i, q in enumerate(self.context.captured_queries))
                raise AssertionError(f"Expected {self.expected_count} queries, but got {actual_count}:\n{queries}")

    return AssertNumQueries
