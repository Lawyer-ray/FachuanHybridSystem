"""
Django Admin E2E 测试 — 当事人管理 (Client)

覆盖 Client 模型的增删改查 Admin 页面。
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 列表页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_client_list_page(admin_page: Page, base_url: str) -> None:
    """访问当事人列表页，验证页面正常加载。"""
    admin_page.goto(f"{base_url}/admin/client/client/")
    admin_page.wait_for_load_state("domcontentloaded")
    # Django admin changelist 应存在 #changelist 或 result_list
    changelist = admin_page.locator("#changelist")
    expect(changelist).to_be_visible()


@pytest.mark.crud
def test_client_search(
    admin_page: Page, base_url: str, e2e_client_entity
) -> None:
    """在列表页使用搜索框搜索当事人名称。"""
    admin_page.goto(f"{base_url}/admin/client/client/")
    admin_page.wait_for_load_state("domcontentloaded")
    searchbar = admin_page.locator("#searchbar")
    expect(searchbar).to_be_visible()
    searchbar.fill(e2e_client_entity.name)
    admin_page.locator("#changelist-search input[type='submit']").click()
    admin_page.wait_for_load_state("domcontentloaded")
    # 搜索结果应包含目标当事人
    result_list = admin_page.locator("#result_list")
    expect(result_list).to_be_visible()
    expect(result_list).to_contain_text(e2e_client_entity.name)


# ------------------------------------------------------------------
# 新增页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_client_add_page(admin_page: Page, base_url: str) -> None:
    """访问当事人新增页，验证表单正常加载。"""
    admin_page.goto(f"{base_url}/admin/client/client/add/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 应存在 change-form
    change_form = admin_page.locator("#change-form")
    expect(change_form).to_be_visible()
    # 验证核心字段存在
    name_input = admin_page.locator("input#id_name")
    expect(name_input).to_be_visible()
    client_type_select = admin_page.locator("select#id_client_type")
    expect(client_type_select).to_be_visible()


@pytest.mark.crud
def test_client_create_natural(admin_page: Page, base_url: str) -> None:
    """创建一个自然人当事人并提交。"""
    admin_page.goto(f"{base_url}/admin/client/client/add/")
    admin_page.wait_for_load_state("domcontentloaded")

    # 填写名称
    admin_page.fill("input#id_name", "自然人测试客户")
    # 选择 client_type = NATURAL
    admin_page.select_option("select#id_client_type", value="natural")
    # 提交
    admin_page.click("input[name='_save']")
    admin_page.wait_for_load_state("domcontentloaded")

    # 成功保存后应跳转回 changelist
    expect(admin_page).to_have_url(f"{base_url}/admin/client/client/")
    # 页面应出现成功消息
    success_msg = admin_page.locator(".messagelist .success")
    expect(success_msg).to_be_visible()


@pytest.mark.crud
def test_client_create_entity(admin_page: Page, base_url: str) -> None:
    """创建一个法人当事人并提交。"""
    admin_page.goto(f"{base_url}/admin/client/client/add/")
    admin_page.wait_for_load_state("domcontentloaded")

    # 选择 client_type = LEGAL（默认值可能已是 legal）
    admin_page.select_option("select#id_client_type", value="legal")
    # 填写名称
    admin_page.fill("input#id_name", "法人测试公司")
    # 填写法定代表人（LEGAL 类型 clean 校验要求此字段）
    admin_page.fill("input#id_legal_representative", "张三")
    # 提交
    admin_page.click("input[name='_save']")
    admin_page.wait_for_load_state("domcontentloaded")

    # 成功保存后应跳转回 changelist
    expect(admin_page).to_have_url(f"{base_url}/admin/client/client/")
    success_msg = admin_page.locator(".messagelist .success")
    expect(success_msg).to_be_visible()


# ------------------------------------------------------------------
# 编辑页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_client_change_page(
    admin_page: Page, base_url: str, e2e_client_entity
) -> None:
    """访问已有当事人的编辑页，验证名称字段正确回显。"""
    url = f"{base_url}/admin/client/client/{e2e_client_entity.pk}/change/"
    admin_page.goto(url)
    admin_page.wait_for_load_state("domcontentloaded")

    change_form = admin_page.locator("#change-form")
    expect(change_form).to_be_visible()
    # 名称字段应显示 fixture 中创建的名称
    name_input = admin_page.locator("input#id_name")
    expect(name_input).to_have_value(e2e_client_entity.name)
