"""
Django Admin E2E 测试 — 证据管理

验证证据列表、证据项列表、证据分组等页面。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_evidence.py -v
    pytest tests/e2e/tests/test_evidence.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 1. 证据列表
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_evidence_list_page(admin_page: Page, base_url: str) -> None:
    """访问证据列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/evidence/evidencelistproxy/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 2. 证据项列表
# ------------------------------------------------------------------

def test_evidence_item_list(admin_page: Page, base_url: str) -> None:
    """访问证据项列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/evidence/evidenceitemproxy/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 3. 证据分组列表
# ------------------------------------------------------------------

def test_evidence_group_list(admin_page: Page, base_url: str) -> None:
    """访问证据分组列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/evidence/evidencegroup/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
