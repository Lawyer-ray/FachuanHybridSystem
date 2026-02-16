"""
测试验证框架功能

验证阶段4新增的验证检测功能是否正常工作
"""
import asyncio
from .base_admin_test import BaseAdminTest
from .validation_scenario import ValidationScenario, Stage4TestReport
from datetime import datetime


async def test_validation_framework():
    """测试验证框架的基本功能"""
    test = BaseAdminTest()
    
    try:
        await test.setup()
        
        print("\n" + "="*80)
        print("测试验证框架功能")
        print("="*80)
        
        # 测试 1: 检查验证错误检测方法是否存在
        print("\n测试 1: 验证方法是否存在")
        assert hasattr(test, 'check_validation_error'), "缺少 check_validation_error 方法"
        assert hasattr(test, 'get_validation_errors'), "缺少 get_validation_errors 方法"
        assert hasattr(test, 'verify_no_validation_errors'), "缺少 verify_no_validation_errors 方法"
        assert hasattr(test, 'wait_for_validation_error'), "缺少 wait_for_validation_error 方法"
        assert hasattr(test, 'fix_validation_error'), "缺少 fix_validation_error 方法"
        print("  ✓ 所有验证方法都存在")
        
        # 测试 2: 测试 ValidationScenario 数据类
        print("\n测试 2: ValidationScenario 数据类")
        scenario = ValidationScenario(
            name="测试场景",
            model="case",
            app="cases",
            invalid_data={"name": ""},
            expected_errors=["此字段是必填项"],
            fix_data={"name": "测试案件"},
            description="测试必填字段验证"
        )
        assert scenario.name == "测试场景"
        assert scenario.model == "case"
        assert scenario.app == "cases"
        print("  ✓ ValidationScenario 数据类正常")
        
        # 测试 3: 测试 Stage4TestReport 数据类
        print("\n测试 3: Stage4TestReport 数据类")
        report = Stage4TestReport(
            total_tests=10,
            passed_tests=8,
            failed_tests=2,
            skipped_tests=0,
            success_rate=80.0,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration=120.5
        )
        assert report.total_tests == 10
        assert report.passed_tests == 8
        assert report.success_rate == 80.0
        print("  ✓ Stage4TestReport 数据类正常")
        
        # 测试 4: 测试报告生成
        print("\n测试 4: 测试报告生成")
        summary = report.generate_summary()
        assert "阶段4测试报告" in summary
        assert "总测试数: 10" in summary
        assert "通过: 8" in summary
        assert "成功率: 80.0%" in summary
        print("  ✓ 报告生成正常")
        
        print("\n" + "="*80)
        print("✓ 所有测试通过")
        print("="*80)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await test.teardown()


if __name__ == "__main__":
    asyncio.run(test_validation_framework())
