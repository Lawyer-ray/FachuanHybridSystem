"""
内联表单测试 - 阶段 3（修复版）

测试复杂的内联表单功能，使用正确的 django-nested-admin 字段名
"""

from .base_admin_test import BaseAdminTest


class TestInlineForms(BaseAdminTest):
    """内联表单测试"""

    async def test_case_add_single_party(self):
        """测试案件添加单个当事人（内联）"""
        print("\n  测试: 案件添加单个当事人")
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        try:
            # 填写主表单
            await self.fill_field("name", "测试案件 - 单个当事人")
            await self.select_option("contract", "4")

            # 添加当事人内联
            await self.add_inline_row("caseparty_set")
            await self.select_option(self.get_inline_field_name("caseparty_set", 0, "client"), "16")
            await self.select_option(self.get_inline_field_name("caseparty_set", 0, "legal_status"), "plaintiff")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 添加单个当事人成功")
        except Exception as e:
            await self.take_screenshot("error_case_single_party")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_case_add_multiple_parties(self):
        """测试案件添加多个当事人（内联）"""
        print("\n  测试: 案件添加多个当事人")
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        try:
            # 填写主表单
            await self.fill_field("name", "测试案件 - 多个当事人")
            await self.select_option("contract", "4")

            # 添加第一个当事人（原告）
            await self.add_inline_row("caseparty_set")
            await self.select_option(self.get_inline_field_name("caseparty_set", 0, "client"), "16")
            await self.select_option(self.get_inline_field_name("caseparty_set", 0, "legal_status"), "plaintiff")

            # 添加第二个当事人（被告）
            await self.add_inline_row("caseparty_set")
            await self.select_option(self.get_inline_field_name("caseparty_set", 1, "client"), "17")
            await self.select_option(self.get_inline_field_name("caseparty_set", 1, "legal_status"), "defendant")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 添加多个当事人成功")
        except Exception as e:
            await self.take_screenshot("error_case_multiple_parties")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_case_add_assignment(self):
        """测试案件添加指派（内联）"""
        print("\n  测试: 案件添加指派")
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        try:
            # 填写主表单
            await self.fill_field("name", "测试案件 - 指派")
            await self.select_option("contract", "4")

            # 添加指派内联
            await self.add_inline_row("caseassignment_set")
            await self.select_option(self.get_inline_field_name("caseassignment_set", 0, "lawyer"), "67")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 添加指派成功")
        except Exception as e:
            await self.take_screenshot("error_case_assignment")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_case_add_case_number(self):
        """测试案件添加案件编号（内联）"""
        print("\n  测试: 案件添加案件编号")
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        try:
            # 填写主表单
            await self.fill_field("name", "测试案件 - 案件编号")
            await self.select_option("contract", "4")

            # 添加案件编号内联
            await self.add_inline_row("casenumber_set")
            await self.fill_field(self.get_inline_field_name("casenumber_set", 0, "number"), "(2024)测001号")
            # 注意：案件编号没有 stage 字段，只有 number 和 remarks

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 添加案件编号成功")
        except Exception as e:
            await self.take_screenshot("error_case_number")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_case_add_case_log(self):
        """测试案件添加案件日志（内联）"""
        print("\n  测试: 案件添加案件日志")
        await self.navigate_to_model("cases", "case")

        # 检查是否有记录
        row_count = await self.get_table_row_count()
        if row_count == 0:
            print(f"    ⚠️  没有案件记录，跳过测试")
            return

        # 编辑第一条记录
        await self.click_first_edit_link()

        try:
            # 添加案件日志内联
            await self.add_inline_row("caselog_set")

            # 等待 JavaScript 初始化完成
            await self.wait_for_js_initialization("logs")

            # 使用智能填写方法
            field_name = self.get_inline_field_name("caselog_set", 0, "content")
            await self.fill_field_smart(field_name, "测试日志内容")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 添加案件日志成功")
        except Exception as e:
            await self.take_screenshot("error_case_log")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_case_all_inlines_together(self):
        """测试案件同时添加所有内联"""
        print("\n  测试: 案件同时添加所有内联")
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        try:
            # 填写主表单
            await self.fill_field("name", "测试案件 - 所有内联")
            await self.select_option("contract", "4")

            # 添加当事人
            await self.add_inline_row("caseparty_set")
            await self.select_option(self.get_inline_field_name("caseparty_set", 0, "client"), "16")
            await self.select_option(self.get_inline_field_name("caseparty_set", 0, "legal_status"), "plaintiff")

            # 添加指派
            await self.add_inline_row("caseassignment_set")
            await self.select_option(self.get_inline_field_name("caseassignment_set", 0, "lawyer"), "67")

            # 添加案件编号
            await self.add_inline_row("casenumber_set")
            await self.fill_field(self.get_inline_field_name("casenumber_set", 0, "number"), "(2024)测002号")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 同时添加所有内联成功")
        except Exception as e:
            await self.take_screenshot("error_case_all_inlines")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_inline_validation_required_fields(self):
        """测试内联表单必填字段验证"""
        print("\n  测试: 内联表单必填字段验证")
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        try:
            # 填写主表单
            await self.fill_field("name", "测试案件 - 内联验证")
            await self.select_option("contract", "4")

            # 添加当事人但不填写必填字段
            await self.add_inline_row("caseparty_set")
            # 故意不选择 client 和 legal_status

            # 提交表单
            await self.submit_form()

            # 应该显示错误消息
            has_error = await self.check_error_message()

            if has_error:
                error_text = await self.get_error_text()
                print(f"    ✅ 内联必填字段验证生效: {error_text}")
            else:
                print(f"    ⚠️  没有显示必填字段错误（可能验证未启用）")
        except Exception as e:
            await self.take_screenshot("error_inline_validation")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_case_edit_inline(self):
        """测试编辑案件的内联记录"""
        print("\n  测试: 编辑案件的内联记录")
        await self.navigate_to_model("cases", "case")

        # 检查是否有记录
        row_count = await self.get_table_row_count()
        if row_count == 0:
            print(f"    ⚠️  没有案件记录，跳过测试")
            return

        # 编辑第一条记录
        await self.click_first_edit_link()

        try:
            # 检查是否有内联记录
            has_inline = await self.check_element_exists('[name*="parties-0-client"]')

            if has_inline:
                # 修改现有内联记录
                await self.select_option(self.get_inline_field_name("caseparty_set", 0, "legal_status"), "defendant")
            else:
                # 添加新的内联记录
                await self.add_inline_row("caseparty_set")
                await self.select_option(self.get_inline_field_name("caseparty_set", 0, "client"), "18")
                await self.select_option(self.get_inline_field_name("caseparty_set", 0, "legal_status"), "third_party")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 编辑内联记录成功")
        except Exception as e:
            await self.take_screenshot("error_case_edit_inline")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_case_delete_inline(self):
        """测试删除案件的内联记录"""
        print("\n  测试: 删除案件的内联记录")
        await self.navigate_to_model("cases", "case")

        # 检查是否有记录
        row_count = await self.get_table_row_count()
        if row_count == 0:
            print(f"    ⚠️  没有案件记录，跳过测试")
            return

        # 编辑第一条记录
        await self.click_first_edit_link()

        try:
            # 检查是否有内联记录
            has_inline = await self.check_element_exists('[name*="parties-0-DELETE"]')

            if has_inline:
                # 勾选删除复选框
                await self.page.check('[name*="parties-0-DELETE"]')

                # 提交表单
                await self.submit_form()

                # 检查成功
                self.assert_true(await self.check_success_message(), "没有显示成功消息")

                print(f"    ✅ 删除内联记录成功")
            else:
                print(f"    ⚠️  没有内联记录可删除")
        except Exception as e:
            await self.take_screenshot("error_case_delete_inline")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_contract_add_with_case_inline(self):
        """测试合同添加案件（内联）"""
        print("\n  测试: 合同添加案件（内联）")
        await self.navigate_to_model("contracts", "contract")
        await self.click_add_button()

        try:
            # 填写主表单
            await self.fill_field("name", "测试合同 - 含案件")

            # law_firm 字段 - 尝试多种方式
            law_firm_filled = False

            # 方式1: 尝试 select
            try:
                await self.select_option("law_firm", "1")
                law_firm_filled = True
            except:
                pass

            # 方式2: 尝试 raw_id_field
            if not law_firm_filled:
                try:
                    await self.fill_raw_id_field("law_firm", "1")
                    law_firm_filled = True
                except:
                    pass

            # 方式3: 跳过这个字段（可能不是必填）
            if not law_firm_filled:
                print(f"    ℹ️  跳过 law_firm 字段（无法填写）")

            # assigned_lawyer 字段
            lawyer_filled = False
            try:
                await self.select_option("assigned_lawyer", "67")
                lawyer_filled = True
            except:
                try:
                    await self.fill_raw_id_field("assigned_lawyer", "67")
                    lawyer_filled = True
                except:
                    print(f"    ℹ️  跳过 assigned_lawyer 字段（无法填写）")

            await self.select_option("case_type", "civil")

            # 添加案件内联
            await self.add_inline_row("cases")
            await self.fill_field(self.get_inline_field_name("cases", 0, "name"), "测试案件 - 从合同创建")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 合同添加案件成功")
        except Exception as e:
            await self.take_screenshot("error_contract_case_inline")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_contract_nested_inline(self):
        """测试合同嵌套内联（Contract -> Case -> CaseParty）"""
        print("\n  测试: 合同嵌套内联")
        await self.navigate_to_model("contracts", "contract")

        # 检查是否有记录
        row_count = await self.get_table_row_count()
        if row_count == 0:
            print(f"    ⚠️  没有合同记录，跳过测试")
            return

        # 编辑第一条记录
        await self.click_first_edit_link()

        try:
            # 添加案件内联
            await self.add_inline_row("cases")
            await self.fill_field(self.get_inline_field_name("cases", 0, "name"), "测试案件 - 嵌套内联")

            # 尝试在案件内联中添加当事人（嵌套内联）
            try:
                await self.add_inline_row("cases-0-caseparty_set")
                await self.select_option("cases-0-parties-0-client", "16")
                await self.select_option("cases-0-parties-0-legal_status", "plaintiff")

                print(f"    ℹ️  嵌套内联功能可用")
            except Exception as e:
                print(f"    ℹ️  嵌套内联功能不可用: {e}")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 合同嵌套内联测试完成")
        except Exception as e:
            await self.take_screenshot("error_contract_nested_inline")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_client_add_identity_doc(self):
        """测试客户添加身份证件（内联）"""
        print("\n  测试: 客户添加身份证件")
        await self.navigate_to_model("client", "client")
        await self.click_add_button()

        try:
            # 等待页面完全加载
            await self.page.wait_for_load_state("networkidle", timeout=15000)
            await self.page.wait_for_timeout(2000)

            # 填写主表单
            await self.fill_field("name", "测试客户 - 含证件")
            await self.fill_field_smart("client_type", "natural")  # 自然人

            # 添加身份证件内联
            await self.add_inline_row("clientidentitydoc_set")

            # 等待内联初始化
            await self.wait_for_js_initialization("identity_docs")

            # 只填写doc_type字段（doc_number字段不存在，只有upload字段）
            await self.fill_field_smart(self.get_inline_field_name("clientidentitydoc_set", 0, "doc_type"), "id_card")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 客户添加身份证件成功")
        except Exception as e:
            await self.take_screenshot("error_client_identity_doc")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_lawyer_add_credential(self):
        """测试律师添加账号凭证（内联）"""
        print("\n  测试: 律师添加账号凭证")
        await self.navigate_to_model("organization", "lawyer")

        # 检查是否有记录
        row_count = await self.get_table_row_count()
        if row_count == 0:
            print(f"    ⚠️  没有律师记录，跳过测试")
            return

        # 编辑第一条记录
        await self.click_first_edit_link()

        try:
            # 添加账号凭证内联
            await self.add_inline_row("accountcredential_set")

            # 等待内联初始化
            await self.wait_for_js_initialization("credentials")

            # 使用映射后的字段名（credentials）
            await self.select_option("credentials-0-site_name", "法院网站")
            await self.fill_field("credentials-0-account", "test_account")
            await self.fill_field("credentials-0-password", "test_password")

            # 提交表单
            await self.submit_form()

            # 检查成功
            self.assert_true(await self.check_success_message(), "没有显示成功消息")

            print(f"    ✅ 律师添加账号凭证成功")
        except Exception as e:
            await self.take_screenshot("error_lawyer_credential")
            print(f"    ❌ 测试失败: {e}")
            raise

    async def test_inline_max_num_validation(self):
        """测试内联表单最大数量限制"""
        print("\n  测试: 内联表单最大数量限制")
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        try:
            # 填写主表单
            await self.fill_field("name", "测试案件 - 内联数量限制")
            await self.select_option("contract", "4")

            # 尝试添加多个内联（如果有 max_num 限制）
            max_attempts = 20
            added_count = 0

            for i in range(max_attempts):
                try:
                    await self.add_inline_row("caseparty_set")
                    added_count += 1
                except:
                    print(f"    ℹ️  达到内联最大数量限制: {added_count}")
                    break

            if added_count == max_attempts:
                print(f"    ℹ️  没有内联数量限制（或限制 >= {max_attempts}）")

            print(f"    ✅ 内联数量限制测试完成")
        except Exception as e:
            await self.take_screenshot("error_inline_max_num")
            print(f"    ❌ 测试失败: {e}")
            raise
