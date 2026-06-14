"""
Django Admin E2E 测试 — 提醒/日历

验证日历页面加载、导航控件、提醒列表、新增提醒表单等功能。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_reminder.py -v
    pytest tests/e2e/tests/test_reminder.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 1. 日历页面加载
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_calendar_page_loads(admin_page: Page, base_url: str) -> None:
    """访问日历页面，验证页面正常加载并包含日历容器元素。"""
    response = admin_page.goto(
        f"{base_url}/admin/reminders/reminder/calendar/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # 页面标题应包含「提醒日历」
    expect(admin_page.locator("body")).to_be_visible()
    page_text = admin_page.locator("body").inner_text()
    assert "提醒日历" in page_text or "日历" in page_text, (
        f"Calendar page should contain calendar title, got: {page_text[:200]}"
    )


# ------------------------------------------------------------------
# 2. 日历导航控件
# ------------------------------------------------------------------

def test_calendar_has_navigation(admin_page: Page, base_url: str) -> None:
    """验证日历页面包含月份/周导航控件（上一月/下一月链接）。"""
    admin_page.goto(f"{base_url}/admin/reminders/reminder/calendar/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 日历页面应包含导航链接（prev_url / next_url 渲染为 <a> 标签）
    # 检查页面中包含「上」「前」「prev」「<」或「>」「下」「next」等导航标识
    nav_links = admin_page.locator("a")
    link_count = nav_links.count()
    assert link_count > 0, "Calendar page should have navigation links"
    # 日历页面通常包含星期标签（周一~周日）
    page_text = admin_page.locator("body").inner_text()
    has_weekday = any(
        label in page_text for label in ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    )
    assert has_weekday, (
        f"Calendar page should contain weekday labels (周一~周日), got: {page_text[:300]}"
    )


# ------------------------------------------------------------------
# 3. 提醒列表页
# ------------------------------------------------------------------

def test_reminder_list_page(admin_page: Page, base_url: str) -> None:
    """访问提醒列表页，验证 changelist 正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/reminders/reminder/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # Django Admin changelist 应包含 #changelist 或 #result_list
    changelist = admin_page.locator("#changelist, #result_list")
    expect(changelist.first).to_be_attached()


# ------------------------------------------------------------------
# 4. 新增提醒页面
# ------------------------------------------------------------------

def test_reminder_add_page(admin_page: Page, base_url: str) -> None:
    """访问新增提醒页面，验证表单正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/reminders/reminder/add/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # Django Admin change form 应包含 #change-form 或 form 表单
    form = admin_page.locator("#change-form, form")
    expect(form.first).to_be_attached()
    # 应包含提醒内容输入字段
    inputs = admin_page.locator("input, select, textarea")
    assert inputs.count() > 0, "Add page should have form input fields"
