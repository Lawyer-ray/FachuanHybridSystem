"""
运行阶段 3：内联表单测试

测试所有内联表单功能
"""

import asyncio
import sys
import time
from datetime import datetime

from .test_inline_forms import TestInlineForms


async def run_stage3_tests():
    """运行阶段 3 测试"""
    print("=" * 80)
    print("Django Admin 测试 - 阶段 3: 内联表单测试")
    print("=" * 80)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    test = TestInlineForms()

    # 测试结果统计
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    skipped_tests = 0
    errors = []

    # 测试列表
    tests = [
        # CaseAdmin 内联测试
        ("案件添加单个当事人", test.test_case_add_single_party),
        ("案件添加多个当事人", test.test_case_add_multiple_parties),
        ("案件添加指派", test.test_case_add_assignment),
        ("案件添加案件编号", test.test_case_add_case_number),
        ("案件添加案件日志", test.test_case_add_case_log),
        ("案件同时添加所有内联", test.test_case_all_inlines_together),
        ("编辑案件的内联记录", test.test_case_edit_inline),
        ("删除案件的内联记录", test.test_case_delete_inline),
        # ContractAdmin 内联测试
        ("合同添加案件（内联）", test.test_contract_add_with_case_inline),
        ("合同嵌套内联", test.test_contract_nested_inline),
        # ClientAdmin 内联测试
        ("客户添加身份证件", test.test_client_add_identity_doc),
        # LawyerAdmin 内联测试
        ("律师添加账号凭证", test.test_lawyer_add_credential),
        # 内联验证测试
        ("内联表单必填字段验证", test.test_inline_validation_required_fields),
        ("内联表单最大数量限制", test.test_inline_max_num_validation),
    ]

    try:
        # 设置测试环境
        print("→ 设置测试环境...")
        await test.setup()
        print("✓ 测试环境设置完成\n")

        # 运行测试
        for test_name, test_func in tests:
            total_tests += 1
            print(f"[{total_tests}/{len(tests)}] 测试: {test_name}")

            start_time = time.time()

            try:
                await test_func()
                passed_tests += 1
                duration = time.time() - start_time
                print(f"  ✅ 通过 ({duration:.2f}s)\n")
            except AssertionError as e:
                failed_tests += 1
                duration = time.time() - start_time
                error_msg = f"断言失败: {e!s}"
                errors.append((test_name, error_msg))
                print(f"  ❌ 失败 ({duration:.2f}s): {error_msg}\n")
            except Exception as e:
                # 检查是否是跳过的测试
                if "跳过" in str(e) or "skip" in str(e).lower():
                    skipped_tests += 1
                    duration = time.time() - start_time
                    print(f"  ⏭️  跳过 ({duration:.2f}s): {e!s}\n")
                else:
                    failed_tests += 1
                    duration = time.time() - start_time
                    error_msg = f"异常: {e!s}"
                    errors.append((test_name, error_msg))
                    print(f"  💥 错误 ({duration:.2f}s): {error_msg}\n")

    finally:
        # 清理测试环境
        print("→ 清理测试环境...")
        await test.teardown()
        print("✓ 测试环境清理完成\n")

    # 打印测试报告
    print("=" * 80)
    print("测试报告 - 阶段 3: 内联表单测试")
    print("=" * 80)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print(f"总测试数: {total_tests}")
    print(f"✅ 通过: {passed_tests}")
    print(f"❌ 失败: {failed_tests}")
    print(f"⏭️  跳过: {skipped_tests}")
    print(f"成功率: {(passed_tests / total_tests * 100):.1f}%")
    print()

    if errors:
        print("失败的测试:")
        print("-" * 80)
        for test_name, error_msg in errors:
            print(f"❌ {test_name}")
            print(f"   {error_msg}")
            print()

    # 生成测试报告文件
    generate_report(total_tests, passed_tests, failed_tests, skipped_tests, errors)

    # 返回退出码
    return 0 if failed_tests == 0 else 1


def generate_report(total, passed, failed, skipped, errors):
    """生成测试报告文件"""
    report_content = f"""# Django Admin 内联表单测试报告 - 阶段 3

**测试日期**: {datetime.now().strftime("%Y-%m-%d")}
**测试阶段**: 阶段 3 - 内联表单测试
**测试人员**: Kiro AI
**测试环境**: macOS, Python 3.12, Django 5.2
**测试状态**: {"✅ 完成" if failed == 0 else "⚠️ 部分完成"}

---

## 📊 测试总结

### 整体结果

- **总测试数**: {total} 个测试用例
- **通过**: {passed} ✅
- **失败**: {failed} ❌
- **跳过**: {skipped} ⏭️
- **成功率**: {(passed / total * 100):.1f}%

### 测试覆盖

#### CaseAdmin 内联测试（8 个）
- 添加单个当事人
- 添加多个当事人
- 添加指派
- 添加案件编号
- 添加案件日志
- 同时添加所有内联
- 编辑内联记录
- 删除内联记录

#### ContractAdmin 内联测试（2 个）
- 添加案件（内联）
- 嵌套内联（Contract -> Case -> CaseParty）

#### ClientAdmin 内联测试（1 个）
- 添加身份证件

#### LawyerAdmin 内联测试（1 个）
- 添加账号凭证

#### 内联验证测试（2 个）
- 必填字段验证
- 最大数量限制

---

## 测试详情

### ✅ 成功的测试

"""

    if passed > 0:
        report_content += f"共 {passed} 个测试通过\n\n"

    if errors:
        report_content += "### ❌ 失败的测试\n\n"
        for test_name, error_msg in errors:
            report_content += f"#### {test_name}\n"
            report_content += f"**错误**: {error_msg}\n\n"

    report_content += f"""
---

## 🔍 问题分析

### 主要发现

1. **内联表单基本功能**
   - 单个内联添加功能
   - 多个内联同时添加功能
   - 内联编辑功能
   - 内联删除功能

2. **嵌套内联功能**
   - 是否支持嵌套内联（需要 nested_admin）
   - 嵌套内联的保存逻辑

3. **内联验证**
   - 必填字段验证
   - 数量限制验证
   - 自定义验证逻辑

---

## 📝 建议

### 立即需要做的

1. **修复失败的测试**
   - 检查选择器是否正确
   - 确认测试数据是否充足
   - 验证内联配置是否正确

2. **优化内联表单**
   - 改进用户体验
   - 添加更多验证
   - 优化性能

3. **文档更新**
   - 记录内联使用方法
   - 添加最佳实践
   - 更新开发指南

---

## 🎯 下一步行动

- [ ] 修复失败的测试
- [ ] 运行阶段 4: 表单验证测试
- [ ] 运行阶段 5: Admin Action 测试
- [ ] 运行阶段 6: 自定义视图测试
- [ ] 运行阶段 7: 性能测试
- [ ] 运行阶段 8: 边界条件测试

---

## 🔄 测试状态

- [x] 阶段 1: 冒烟测试 - ✅ 完成
- [x] 阶段 2: CRUD 测试 - ⚠️ 部分完成
- [x] 阶段 3: 内联表单测试 - {"✅ 完成" if failed == 0 else "⚠️ 部分完成"}
- [ ] 阶段 4: 表单验证测试 - 待执行
- [ ] 阶段 5: Admin Action 测试 - 待执行
- [ ] 阶段 6: 自定义视图测试 - 待执行
- [ ] 阶段 7: 性能测试 - 待执行
- [ ] 阶段 8: 边界条件测试 - 待执行

---

**报告生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

    # 写入报告文件
    with open("backend/tests/admin/TEST_REPORT_STAGE3.md", "w", encoding="utf-8") as f:
        f.write(report_content)

    print("✓ 测试报告已生成: backend/tests/admin/TEST_REPORT_STAGE3.md")


if __name__ == "__main__":
    exit_code = asyncio.run(run_stage3_tests())
    sys.exit(exit_code)
