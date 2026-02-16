"""
测试验证错误检测方法

验证新添加的错误检测方法是否正常工作
"""

import asyncio

from .base_admin_test import BaseAdminTest


class TestValidationDetection(BaseAdminTest):
    """测试验证错误检测"""

    async def test_detect_required_field_error(self):
        """测试检测必填字段错误"""
        print("\n" + "=" * 70)
        print("测试: 检测必填字段错误")
        print("=" * 70)

        # 导航到案件添加页面
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        # 不填写必填字段，直接提交
        await self.submit_form()

        # 检查是否有验证错误
        has_error = await self.check_validation_error()

        if has_error:
            print("✅ 成功检测到验证错误")

            # 获取所有错误
            errors = await self.get_validation_errors()
            print(f"✅ 找到 {len(errors)} 个错误")

            return True
        else:
            print("❌ 未检测到验证错误")
            return False

    async def test_detect_specific_field_error(self):
        """测试检测特定字段的错误"""
        print("\n" + "=" * 70)
        print("测试: 检测特定字段错误")
        print("=" * 70)

        # 导航到案件添加页面
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        # 不填写必填字段，直接提交
        await self.submit_form()

        # 检查特定字段的错误（如 name 字段）
        has_name_error = await self.check_validation_error(field_name="name")

        if has_name_error:
            print("✅ 成功检测到 name 字段的验证错误")
            return True
        else:
            print("❌ 未检测到 name 字段的验证错误")
            return False

    async def test_verify_no_errors_after_fix(self):
        """测试修正错误后没有验证错误"""
        print("\n" + "=" * 70)
        print("测试: 修正错误后验证没有错误")
        print("=" * 70)

        # 导航到案件添加页面
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        # 填写所有必填字段
        await self.fill_field("name", "测试案件 - 验证检测")
        await self.select_option("contract", "4")  # 假设有ID为4的合同

        # 提交表单
        await self.submit_form()

        # 验证没有错误
        no_errors = await self.verify_no_validation_errors()

        if no_errors:
            print("✅ 确认没有验证错误")
            return True
        else:
            print("❌ 仍然有验证错误")
            return False

    async def test_get_all_errors(self):
        """测试获取所有错误"""
        print("\n" + "=" * 70)
        print("测试: 获取所有验证错误")
        print("=" * 70)

        # 导航到案件添加页面
        await self.navigate_to_model("cases", "case")
        await self.click_add_button()

        # 不填写任何字段，直接提交
        await self.submit_form()

        # 获取所有错误
        errors = await self.get_validation_errors()

        if errors:
            print(f"✅ 成功获取 {len(errors)} 个错误")
            print("\n错误详情:")
            for i, error in enumerate(errors, 1):
                print(f"  {i}. 字段: {error['field']}")
                print(f"     消息: {error['message']}")
                print(f"     位置: {error['location']}")
            return True
        else:
            print("❌ 未获取到任何错误")
            return False


async def main():
    """运行所有测试"""
    test = TestValidationDetection()

    try:
        await test.setup()

        results = []

        # 测试1: 检测必填字段错误
        try:
            result = await test.test_detect_required_field_error()
            results.append(("检测必填字段错误", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("检测必填字段错误", False))

        # 测试2: 检测特定字段错误
        try:
            result = await test.test_detect_specific_field_error()
            results.append(("检测特定字段错误", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("检测特定字段错误", False))

        # 测试3: 获取所有错误
        try:
            result = await test.test_get_all_errors()
            results.append(("获取所有错误", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("获取所有错误", False))

        # 测试4: 验证没有错误（这个可能会失败，因为需要有效的合同ID）
        try:
            result = await test.test_verify_no_errors_after_fix()
            results.append(("验证没有错误", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("验证没有错误", False))

        # 打印测试结果
        print("\n" + "=" * 70)
        print("测试结果汇总")
        print("=" * 70)

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for test_name, result in results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{status}: {test_name}")

        print(f"\n总计: {passed}/{total} 通过 ({passed/total*100:.1f}%)")

    finally:
        await test.teardown()


if __name__ == "__main__":
    asyncio.run(main())
