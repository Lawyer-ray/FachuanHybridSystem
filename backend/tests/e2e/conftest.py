"""
Django Admin E2E 测试 — Playwright Fixtures

使用 pytest-playwright + pytest-django 的 live_server fixture。
浏览器自动化操作 Django Admin 页面，模拟真实用户行为。

运行方式（推荐使用脚本，自动设置环境变量）：
    cd backend
    bash tests/e2e/run_e2e.sh                           # 运行全部
    bash tests/e2e/run_e2e.sh tests/e2e/tests/test_auth.py  # 指定文件
    bash tests/e2e/run_e2e.sh --headed                  # 有头模式

或手动设置环境变量：
    DATABASE_PATH=/tmp/e2e_test.sqlite3 DJANGO_ALLOW_ASYNC_UNSAFE=true \\
        pytest tests/e2e/ -v --timeout=120 --reuse-db
"""

import os
import sys
from typing import Any

import pytest
from playwright.sync_api import Page, expect

# 添加项目路径（与 backend/conftest.py 保持一致）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apiSystem"))

# Playwright 使用 asyncio 内部，Django 的同步 ORM 需要此开关
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

# E2E 测试专用用户名/密码
E2E_USERNAME = "e2e_admin"
E2E_PASSWORD = "E2Etest@2026"


# ------------------------------------------------------------------
# 测试数据 Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def e2e_user(db: Any) -> Any:
    """创建 E2E 测试管理员用户"""
    from apps.organization.models import LawFirm, Lawyer

    firm, _ = LawFirm.objects.get_or_create(name="E2E测试律所")
    user = Lawyer.objects.create_user(
        username=E2E_USERNAME,
        password=E2E_PASSWORD,
        real_name="E2E测试律师",
        is_admin=True,
        is_superuser=True,
        is_staff=True,
        law_firm=firm,
    )
    return user


@pytest.fixture
def e2e_firm(e2e_user: Any) -> Any:
    """返回 E2E 测试律所"""
    from apps.organization.models import LawFirm

    return LawFirm.objects.get(name="E2E测试律所")


@pytest.fixture
def e2e_client_entity(db: Any, e2e_user: Any) -> Any:
    """创建 E2E 测试当事人"""
    from apps.client.models import Client

    return Client.objects.create(
        name="E2E测试当事人",
        client_type=Client.NATURAL,
        is_our_client=True,
    )


@pytest.fixture
def e2e_contract(db: Any, e2e_user: Any) -> Any:
    """创建 E2E 测试合同"""
    from apps.contracts.models import Contract

    return Contract.objects.create(
        name="E2E测试合同",
        case_type="civil",
    )


@pytest.fixture
def e2e_case(db: Any, e2e_contract: Any) -> Any:
    """创建 E2E 测试案件"""
    from apps.cases.models import Case

    return Case.objects.create(
        name="E2E测试案件",
        contract=e2e_contract,
    )


@pytest.fixture
def e2e_full_data(db: Any, e2e_user: Any, e2e_client_entity: Any, e2e_contract: Any, e2e_case: Any) -> dict:
    """创建完整的 E2E 测试数据链"""
    return {
        "user": e2e_user,
        "client": e2e_client_entity,
        "contract": e2e_contract,
        "case": e2e_case,
    }


# ------------------------------------------------------------------
# Playwright 页面 Fixtures
# ------------------------------------------------------------------


def _clear_admin_login_rate_limit() -> None:
    """清掉 `/admin/login/` 的限流计数。

    `admin_customization.py` 用 `@rate_limit_from_settings("AUTH")` 包了
    `admin.site.login`（5 次/60s），而 `admin_page` fixture **每个用例都要登一次**。
    限流计数存在 Django 缓存里跨用例累积——一个文件跑到第 3 个用例就被 429 拦下，
    登录页渲染成「请求过于频繁」，后续 `Locator.fill` 全部超时。

    这是「套件每用例都登录」与「登录端点按 IP 限流」之间的固有不匹配，与业务无关。
    这里只删测试侧的限流 key，**不改动生产代码**（改生产代码会让限流在
    pytest 下整体失效，把 `test_admin_login_rate_limited` 这类单测打成假绿）。
    """
    import hashlib
    import time

    from django.core.cache import cache

    # `rate_limit_from_settings` 默认 by_user=True，走 `rate_limit_by_user` 的
    # key_func：匿名请求返回 `ip:<ip>`（**不带 path**，与 RateLimiter 默认的
    # `ip:path` 不同），已认证返回 `user:<id>`。登录请求尚未认证，故只需清 ip 桶。
    identifiers = [f"ip:{ip}" for ip in ("127.0.0.1", "::1")]
    identifiers.append("user:1")  # e2e_user 是每条用例新建的用户，id 从 1 起
    bucket = int(time.time()) // 60
    for identifier in identifiers:
        key_hash = hashlib.md5(identifier.encode(), usedforsecurity=False).hexdigest()[:16]
        # 覆盖当前窗口与相邻窗口，避免跨分钟边界漏删
        for offset in (0, -1, 1):
            cache.delete(f"ratelimit:{key_hash}:{bucket + offset}")


@pytest.fixture
def admin_page(page: Page, e2e_user: Any, live_server: Any) -> Page:
    """
    已登录的 Django Admin 页面。

    每个测试用例：
    1. 创建测试用户（通过 e2e_user fixture）
    2. 清掉 admin 登录限流计数（见下）
    3. 打开 Django Admin 登录页
    4. 填写用户名密码并提交
    5. 等待跳转到 Admin 首页
    6. 返回已认证的 page 对象
    """
    base_url = live_server.url
    _clear_admin_login_rate_limit()
    page.goto(f"{base_url}/admin/login/")
    page.wait_for_load_state("networkidle")
    # 登录页有登录+注册两个表单，选择第一个（登录表单）
    page.locator("#id_username").first.fill(E2E_USERNAME)
    page.locator("#id_password").first.fill(E2E_PASSWORD)
    # 登录页有 CSS 滑入动画，force=True 绕过动画期间的 pointer events 拦截
    page.locator("button[type='submit']").first.click(force=True)
    # 等待登录成功（跳转到 admin 首页或日历页）
    page.wait_for_url("**/admin/**")
    # 附加 base_url 到 page 对象，方便测试中使用
    page._e2e_base_url = base_url  # type: ignore[attr-defined]
    return page


@pytest.fixture(scope="session")
def base_url(live_server: Any) -> str:
    """返回 live_server 的 base URL（session 级别，兼容 pytest-base-url 插件）"""
    return live_server.url
