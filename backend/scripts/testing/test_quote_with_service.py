#!/usr/bin/env python3
"""
使用 PreservationQuoteService 测试完整询价流程

这个脚本测试：
1. Token 管理（10分钟过期）
2. 保全金额格式转换
3. 询价 API 调用
"""

import asyncio
import os
import sys
from decimal import Decimal

import django

from apps.core.path import Path

# 设置 Django 环境
backend_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(backend_root))
sys.path.insert(0, str(backend_root / "apiSystem"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.apiSystem.settings")
django.setup()


async def test_quote_service():
    """测试询价服务"""
    from apps.automation.services.insurance.preservation_quote_service import PreservationQuoteService

    print("\n" + "=" * 100)
    print("🚀 测试询价服务")
    print("=" * 100)

    # 创建服务
    service = PreservationQuoteService()

    # 测试参数
    preserve_amount = Decimal("3")  # 3 万元
    corp_id = "2550"  # 法院 ID
    category_id = "category_id_here"  # 分类 ID（需要替换）
    credential_id = 1  # 凭证 ID（需要替换）

    print(f"\n📋 测试参数:")
    print(f"   保全金额: {preserve_amount} 万元")
    print(f"   保全金额类型: {type(preserve_amount)}")
    print(f"   保全金额转整数: {int(preserve_amount)}")
    print(f"   法院 ID: {corp_id}")
    print(f"   分类 ID: {category_id}")
    print(f"   凭证 ID: {credential_id}")

    try:
        # 1. 创建询价任务
        print(f"\n" + "=" * 100)
        print("📝 步骤 1: 创建询价任务")
        print("=" * 100)

        quote = service.create_quote(
            preserve_amount=preserve_amount,
            corp_id=corp_id,
            category_id=category_id,
            credential_id=credential_id,
        )

        print(f"✅ 询价任务创建成功")
        print(f"   任务 ID: {quote.id}")
        print(f"   状态: {quote.status}")

        # 2. 执行询价
        print(f"\n" + "=" * 100)
        print("🔄 步骤 2: 执行询价")
        print("=" * 100)

        result = await service.execute_quote(quote.id)

        print(f"\n" + "=" * 100)
        print("📊 询价结果")
        print("=" * 100)
        print(f"   任务 ID: {result['quote_id']}")
        print(f"   状态: {result['status']}")
        print(f"   保险公司总数: {result['total_companies']}")
        print(f"   成功数量: {result['success_count']}")
        print(f"   失败数量: {result['failed_count']}")
        print(f"   执行时间: {result['execution_time']:.2f} 秒")

        # 3. 获取详细结果
        print(f"\n" + "=" * 100)
        print("📋 步骤 3: 获取详细结果")
        print("=" * 100)

        quote = service.get_quote(quote.id)

        print(f"\n成功的报价:")
        for insurance_quote in quote.quotes.filter(status="success"):
            print(f"   {insurance_quote.company_name}: ¥{insurance_quote.premium}")

        print(f"\n失败的报价:")
        for insurance_quote in quote.quotes.filter(status="failed"):
            print(f"   {insurance_quote.company_name}: {insurance_quote.error_message}")

        print(f"\n" + "=" * 100)
        print("✅ 测试完成")
        print("=" * 100)

    except Exception as e:
        print(f"\n" + "=" * 100)
        print("❌ 测试失败")
        print("=" * 100)
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("\n🚀 开始测试询价服务\n")
    asyncio.run(test_quote_service())
