"""
快速测试 - 只测试失败的3个用例
"""

import asyncio

from .test_inline_forms import TestInlineForms


async def main():
    """运行快速测试"""
    test = TestInlineForms()

    try:
        await test.setup()

        print("\n" + "=" * 70)
        print("快速测试 - 只测试失败的2个用例")
        print("=" * 70)

        # 测试1: 客户身份证件
        try:
            await test.test_client_add_identity_doc()
            print("✅ 客户身份证件测试通过")
        except Exception as e:
            print(f"❌ 客户身份证件测试失败: {e}")

        # 测试2: 律师凭证
        try:
            await test.test_lawyer_add_credential()
            print("✅ 律师凭证测试通过")
        except Exception as e:
            print(f"❌ 律师凭证测试失败: {e}")

    finally:
        await test.teardown()


if __name__ == "__main__":
    asyncio.run(main())
