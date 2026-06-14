"""
Django Admin E2E 测试 — 合同管理 (Contract)

覆盖 Contract 模型的增删改查 Admin 页面及批量文件夹绑定页面。
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 列表页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_contract_list_page(admin_page: Page, base_url: str) -> None:
    """访问合同列表页，验证页面正常加载。"""
    admin_page.goto(f"{base_url}/admin/contracts/contract/")
    admin_page.wait_for_load_state("domcontentloaded")
    changelist = admin_page.locator("#changelist")
    expect(changelist).to_be_visible()


@pytest.mark.crud
def test_contract_search(
    admin_page: Page, base_url: str, e2e_contract
) -> None:
    """在列表页使用搜索框搜索合同名称。"""
    admin_page.goto(f"{base_url}/admin/contracts/contract/")
    admin_page.wait_for_load_state("domcontentloaded")
    searchbar = admin_page.locator("#searchbar")
    expect(searchbar).to_be_visible()
    searchbar.fill(e2e_contract.name)
    admin_page.locator("#changelist-search input[type='submit']").click()
    admin_page.wait_for_load_state("domcontentloaded")
    result_list = admin_page.locator("#result_list")
    expect(result_list).to_be_visible()
    expect(result_list).to_contain_text(e2e_contract.name)


# ------------------------------------------------------------------
# 新增页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_contract_add_page(admin_page: Page, base_url: str) -> None:
    """访问合同新增页，验证表单正常加载。"""
    admin_page.goto(f"{base_url}/admin/contracts/contract/add/")
    admin_page.wait_for_load_state("domcontentloaded")
    change_form = admin_page.locator("#change-form")
    expect(change_form).to_be_visible()
    # 验证核心字段存在
    name_input = admin_page.locator("input#id_name")
    expect(name_input).to_be_visible()
    case_type_select = admin_page.locator("select#id_case_type")
    expect(case_type_select).to_be_visible()


@pytest.mark.crud
def test_contract_create(admin_page: Page, base_url: str) -> None:
    """创建一个合同并提交。"""
    admin_page.goto(f"{base_url}/admin/contracts/contract/add/")
    admin_page.wait_for_load_state("domcontentloaded")

    admin_page.fill("input#id_name", "E2E新合同")
    admin_page.select_option("select#id_case_type", value="civil")
    # 提交
    admin_page.click("input[name='_save']")
    admin_page.wait_for_load_state("domcontentloaded")

    # 成功保存后应跳转回 changelist
    expect(admin_page).to_have_url(f"{base_url}/admin/contracts/contract/")
    success_msg = admin_page.locator(".messagelist .success")
    expect(success_msg).to_be_visible()


# ------------------------------------------------------------------
# 编辑页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_contract_change_page(
    admin_page: Page, base_url: str, e2e_contract
) -> None:
    """访问已有合同的编辑页，验证名称字段正确回显。"""
    url = f"{base_url}/admin/contracts/contract/{e2e_contract.pk}/change/"
    admin_page.goto(url)
    admin_page.wait_for_load_state("domcontentloaded")

    change_form = admin_page.locator("#change-form")
    expect(change_form).to_be_visible()
    name_input = admin_page.locator("input#id_name")
    expect(name_input).to_have_value(e2e_contract.name)


# ------------------------------------------------------------------
# 批量文件夹绑定
# ------------------------------------------------------------------


@pytest.mark.crud
def test_batch_folder_binding_page(admin_page: Page, base_url: str) -> None:
    """访问合同批量文件夹绑定页面，验证页面正常加载。"""
    admin_page.goto(f"{base_url}/admin/contracts/contract/batch-folder-binding/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 自定义页面应有 body 内容（至少不报 500）
    body = admin_page.locator("body")
    expect(body).to_be_visible()
    # 页面不应出现 Django 错误页
    error_note = admin_page.locator("#traceback")
    expect(error_note).not_to_be_visible()
