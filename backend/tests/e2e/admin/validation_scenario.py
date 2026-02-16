"""
验证场景数据类

用于封装表单验证测试场景
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ValidationError:
    """验证错误"""

    field: str  # 字段名
    message: str  # 错误消息
    location: str  # 错误位置（main_form/inline）
    inline_index: Optional[int] = None  # 内联索引（如果是内联错误）


@dataclass
class ValidationTestResult:
    """验证测试结果"""

    scenario_name: str  # 场景名称
    passed: bool  # 是否通过
    errors_detected: List[ValidationError]  # 检测到的错误
    errors_expected: List[str]  # 期望的错误
    execution_time: float  # 执行时间（秒）
    screenshots: List[str]  # 截图路径
    error_message: Optional[str] = None  # 失败原因


@dataclass
class ValidationScenario:
    """
    验证场景

    封装一个完整的验证测试场景，包括：
    - 场景信息（名称、描述）
    - 目标模型（app、model）
    - 测试数据（无效数据、期望错误、修正数据）
    """

    name: str  # 场景名称
    model: str  # 模型名称
    app: str  # 应用名称
    invalid_data: Dict[str, Any]  # 无效数据
    expected_errors: List[str]  # 期望的错误消息
    fix_data: Dict[str, Any]  # 修正数据
    description: str = ""  # 场景描述

    async def execute(self, test_case) -> ValidationTestResult:
        """
        执行验证场景

        Args:
            test_case: 测试用例实例（BaseAdminTest 或其子类）

        Returns:
            测试结果
        """
        import time

        print(f"\n{'='*60}")
        print(f"执行验证场景: {self.name}")
        print(f"描述: {self.description}")
        print(f"{'='*60}")

        start_time = time.time()
        screenshots = []
        errors_detected = []

        try:
            # 1. 导航到添加页面
            await test_case.navigate_to_model(self.app, self.model)
            await test_case.click_add_button()

            # 2. 填写无效数据
            print(f"\n步骤 1: 填写无效数据")
            for field_name, value in self.invalid_data.items():
                try:
                    await test_case.fill_field_smart(field_name, str(value))
                except Exception as e:
                    print(f"  ⚠️  填写字段失败: {field_name} - {e}")

            # 3. 提交表单
            print(f"\n步骤 2: 提交表单")
            await test_case.submit_form()

            # 截图：提交后
            screenshot_name = f"{self.name}_after_submit"
            await test_case.take_screenshot(screenshot_name)
            screenshots.append(screenshot_name)

            # 4. 等待验证错误出现
            print(f"\n步骤 3: 等待验证错误")
            error_appeared = await test_case.wait_for_validation_error(timeout=5000)

            if not error_appeared:
                print(f"  ⚠️  未检测到验证错误（可能验证通过了）")

            # 5. 获取所有验证错误
            print(f"\n步骤 4: 获取验证错误")
            errors = await test_case.get_validation_errors()

            # 转换为 ValidationError 对象
            for error in errors:
                errors_detected.append(
                    ValidationError(field=error["field"], message=error["message"], location=error["location"])
                )

            # 6. 验证错误消息是否符合预期
            print(f"\n步骤 5: 验证错误消息")
            all_error_messages = [e.message for e in errors_detected]

            # 检查是否所有期望的错误都出现了
            missing_errors = []
            for expected_error in self.expected_errors:
                found = False
                for actual_message in all_error_messages:
                    if expected_error in actual_message:
                        found = True
                        break

                if not found:
                    missing_errors.append(expected_error)

            if missing_errors:
                print(f"  ⚠️  缺少期望的错误消息:")
                for missing in missing_errors:
                    print(f"    - {missing}")
            else:
                print(f"  ✓ 所有期望的错误消息都出现了")

            # 7. 修正错误
            print(f"\n步骤 6: 修正错误")
            for field_name, correct_value in self.fix_data.items():
                try:
                    await test_case.fix_validation_error(field_name, str(correct_value))
                except Exception as e:
                    print(f"  ⚠️  修正字段失败: {field_name} - {e}")

            # 8. 重新提交
            print(f"\n步骤 7: 重新提交表单")
            await test_case.submit_form()

            # 截图：修正后提交
            screenshot_name = f"{self.name}_after_fix"
            await test_case.take_screenshot(screenshot_name)
            screenshots.append(screenshot_name)

            # 9. 验证是否成功
            print(f"\n步骤 8: 验证是否成功")
            success = await test_case.check_success_message()
            no_errors = await test_case.verify_no_validation_errors()

            # 计算执行时间
            execution_time = time.time() - start_time

            # 判断测试是否通过
            passed = (
                len(errors_detected) > 0  # 检测到了错误
                and len(missing_errors) == 0  # 所有期望的错误都出现了
                and success  # 修正后保存成功
                and no_errors  # 修正后没有错误
            )

            if passed:
                print(f"\n{'='*60}")
                print(f"✓ 场景通过: {self.name}")
                print(f"{'='*60}")
            else:
                print(f"\n{'='*60}")
                print(f"✗ 场景失败: {self.name}")
                if len(errors_detected) == 0:
                    print(f"  原因: 未检测到验证错误")
                elif len(missing_errors) > 0:
                    print(f"  原因: 缺少期望的错误消息")
                elif not success:
                    print(f"  原因: 修正后保存失败")
                elif not no_errors:
                    print(f"  原因: 修正后仍有验证错误")
                print(f"{'='*60}")

            return ValidationTestResult(
                scenario_name=self.name,
                passed=passed,
                errors_detected=errors_detected,
                errors_expected=self.expected_errors,
                execution_time=execution_time,
                screenshots=screenshots,
                error_message=None if passed else "场景执行失败",
            )

        except Exception as e:
            # 异常处理
            execution_time = time.time() - start_time

            print(f"\n{'='*60}")
            print(f"✗ 场景异常: {self.name}")
            print(f"  错误: {e}")
            print(f"{'='*60}")

            # 截图：异常时
            screenshot_name = f"{self.name}_exception"
            try:
                await test_case.take_screenshot(screenshot_name)
                screenshots.append(screenshot_name)
            except:
                pass

            return ValidationTestResult(
                scenario_name=self.name,
                passed=False,
                errors_detected=errors_detected,
                errors_expected=self.expected_errors,
                execution_time=execution_time,
                screenshots=screenshots,
                error_message=str(e),
            )


@dataclass
class Stage4TestReport:
    """阶段4测试报告"""

    total_tests: int  # 总测试数
    passed_tests: int  # 通过测试数
    failed_tests: int  # 失败测试数
    skipped_tests: int  # 跳过测试数
    success_rate: float  # 成功率
    results: List[ValidationTestResult] = field(default_factory=list)  # 测试结果
    start_time: Optional[datetime] = None  # 开始时间
    end_time: Optional[datetime] = None  # 结束时间
    duration: float = 0.0  # 总耗时（秒）

    def generate_summary(self) -> str:
        """生成测试摘要"""
        lines = []
        lines.append("=" * 80)
        lines.append("阶段4测试报告 - Django Admin 表单验证测试")
        lines.append("=" * 80)
        lines.append("")

        # 统计信息
        lines.append(f"总测试数: {self.total_tests}")
        lines.append(f"通过: {self.passed_tests}")
        lines.append(f"失败: {self.failed_tests}")
        lines.append(f"跳过: {self.skipped_tests}")
        lines.append(f"成功率: {self.success_rate:.1f}%")
        lines.append(f"总耗时: {self.duration:.2f} 秒")
        lines.append("")

        # 时间信息
        if self.start_time and self.end_time:
            lines.append(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"结束时间: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")

        # 详细结果
        lines.append("=" * 80)
        lines.append("详细结果")
        lines.append("=" * 80)
        lines.append("")

        for i, result in enumerate(self.results, 1):
            status = "✓ 通过" if result.passed else "✗ 失败"
            lines.append(f"{i}. {result.scenario_name}: {status}")
            lines.append(f"   执行时间: {result.execution_time:.2f} 秒")
            lines.append(f"   检测到的错误: {len(result.errors_detected)}")
            lines.append(f"   期望的错误: {len(result.errors_expected)}")

            if not result.passed and result.error_message:
                lines.append(f"   失败原因: {result.error_message}")

            lines.append("")

        return "\n".join(lines)

    def save_to_file(self, filename: str = "STAGE4_TEST_REPORT.md"):
        """保存报告到文件"""
        import os

        report_dir = "backend/tests/admin"
        if not os.path.exists(report_dir):
            os.makedirs(report_dir)

        filepath = os.path.join(report_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.generate_summary())

        print(f"\n报告已保存: {filepath}")
