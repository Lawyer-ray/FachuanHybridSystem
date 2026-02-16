#!/usr/bin/env python3
"""
生成 Mypy 错误修复优先级和路线图

按模块重要性和错误复杂度排序，生成分阶段修复计划
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# 模块重要性权重（1-10，10最重要）
MODULE_IMPORTANCE: dict[str, int] = {
    "apps/core": 10,  # 核心基础设施，影响所有模块
    "apps/litigation_ai": 9,  # AI核心功能
    "apps/cases": 8,  # 核心业务
    "apps/documents": 7,  # 核心业务
    "apps/contracts": 7,  # 核心业务
    "apps/client": 6,  # 基础业务
    "apps/organization": 6,  # 基础业务
    "apps/automation": 5,  # 自动化服务，第三方库多
    "apps/chat_records": 4,  # 辅助功能
    "apps/reminders": 3,  # 辅助功能
}


# 错误类型复杂度（1-10，1最简单）
ERROR_COMPLEXITY: dict[str, int] = {
    # 简单错误（批量修复）
    "type-arg": 1,  # 泛型参数缺失
    "no-untyped-def": 2,  # 函数缺少类型注解
    "var-annotated": 2,  # 变量缺少类型注解
    "no-untyped-call": 3,  # 调用无类型函数
    
    # 中等错误（需要分析）
    "no-any-return": 4,  # 返回Any
    "attr-defined": 5,  # 属性未定义（Django ORM）
    "assignment": 5,  # 赋值类型不兼容
    "arg-type": 5,  # 参数类型不匹配
    "return-value": 5,  # 返回值类型不匹配
    
    # 复杂错误（手动修复）
    "valid-type": 6,  # 类型无效
    "call-arg": 6,  # 调用参数错误
    "name-defined": 7,  # 变量未定义
    "union-attr": 7,  # Union类型属性访问
    "func-returns-value": 7,  # 函数返回值问题
    "no-redef": 8,  # 重复定义
    "operator": 8,  # 运算符类型错误
    "index": 8,  # 索引类型错误
    "misc": 9,  # 其他错误
    "abstract": 9,  # 抽象类错误
    "redundant-cast": 2,  # 冗余cast（简单）
}


def parse_error_analysis(file_path: Path) -> dict[str, Any]:
    """解析错误分析文件"""
    content = file_path.read_text(encoding="utf-8")
    
    data: dict[str, Any] = {
        "total_errors": 0,
        "modules": {},
        "error_types": {},
    }
    
    lines = content.split("\n")
    current_section = ""
    
    for line in lines:
        line = line.strip()
        
        if "总错误数:" in line:
            data["total_errors"] = int(line.split(":")[1].strip())
        
        elif "按模块统计错误数" in line:
            current_section = "modules"
        
        elif "按错误类型统计" in line:
            current_section = "error_types"
        
        elif "高错误模块" in line:
            current_section = "high_error_modules"
        
        elif current_section == "modules" and line and line[0].isdigit():
            # 解析模块行：1. apps/automation  1600 (39.99%)
            parts = line.split()
            if len(parts) >= 3:
                module = parts[1]
                count = int(parts[2])
                data["modules"][module] = count
        
        elif current_section == "error_types" and line and line[0].isdigit():
            # 解析错误类型行：1. no-untyped-def  851 (21.27%)
            parts = line.split()
            if len(parts) >= 3:
                error_type = parts[1]
                count = int(parts[2])
                data["error_types"][error_type] = count
    
    return data


def calculate_module_priority(
    module: str, 
    error_count: int, 
    total_errors: int
) -> float:
    """
    计算模块修复优先级
    
    优先级 = 重要性权重 * 0.6 + (1 - 错误占比) * 0.4
    
    重要性高且错误少的模块优先修复（快速见效）
    """
    importance = MODULE_IMPORTANCE.get(module, 5)
    error_ratio = error_count / total_errors
    
    # 重要性占60%，错误少占40%
    priority = (importance / 10) * 0.6 + (1 - error_ratio) * 0.4
    
    return priority


def calculate_error_type_priority(error_type: str, count: int) -> float:
    """
    计算错误类型修复优先级
    
    优先级 = (1 / 复杂度) * 0.7 + (数量占比) * 0.3
    
    简单且数量多的错误优先修复（批量处理）
    """
    complexity = ERROR_COMPLEXITY.get(error_type, 5)
    
    # 简单度占70%，数量占30%
    priority = (1 / complexity) * 0.7 + (count / 1000) * 0.3
    
    return priority


def generate_priority_report(data: dict[str, Any]) -> None:
    """生成修复优先级报告"""
    total_errors = data["total_errors"]
    modules = data["modules"]
    error_types = data["error_types"]
    
    logger.info("\n" + "=" * 80)
    logger.info("Mypy 错误修复优先级报告")
    logger.info("=" * 80)
    logger.info(f"\n总错误数: {total_errors}\n")
    
    # 1. 按模块重要性排序
    logger.info("=" * 80)
    logger.info("模块修复优先级（按重要性和错误数排序）")
    logger.info("=" * 80)
    
    module_priorities = []
    for module, count in modules.items():
        priority = calculate_module_priority(module, count, total_errors)
        importance = MODULE_IMPORTANCE.get(module, 5)
        module_priorities.append((module, count, importance, priority))
    
    # 按优先级降序排序
    module_priorities.sort(key=lambda x: x[3], reverse=True)
    
    logger.info(f"\n{'排名':<4} {'模块':<40} {'错误数':<8} {'重要性':<8} {'优先级':<8}")
    logger.info("-" * 80)
    
    for i, (module, count, importance, priority) in enumerate(module_priorities, 1):
        logger.info(
            f"{i:<4} {module:<40} {count:<8} {importance:<8} {priority:.2f}"
        )
    
    # 2. 按错误复杂度分类
    logger.info("\n" + "=" * 80)
    logger.info("错误类型修复优先级（按复杂度和数量排序）")
    logger.info("=" * 80)
    
    error_priorities = []
    for error_type, count in error_types.items():
        priority = calculate_error_type_priority(error_type, count)
        complexity = ERROR_COMPLEXITY.get(error_type, 5)
        error_priorities.append((error_type, count, complexity, priority))
    
    # 按优先级降序排序
    error_priorities.sort(key=lambda x: x[3], reverse=True)
    
    logger.info(f"\n{'排名':<4} {'错误类型':<25} {'数量':<8} {'复杂度':<8} {'优先级':<8}")
    logger.info("-" * 80)
    
    for i, (error_type, count, complexity, priority) in enumerate(error_priorities, 1):
        logger.info(
            f"{i:<4} {error_type:<25} {count:<8} {complexity:<8} {priority:.2f}"
        )
    
    # 3. 生成修复路线图
    logger.info("\n" + "=" * 80)
    logger.info("修复路线图")
    logger.info("=" * 80)
    
    logger.info("\n【阶段1：全局简单错误批量修复】（预计2-3天，减少50%错误）")
    logger.info("优先修复简单、高频的错误类型，快速降低错误总数")
    logger.info("\n修复目标：")
    
    simple_errors = [
        (et, c) for et, c, comp, _ in error_priorities 
        if comp <= 3
    ]
    
    phase1_total = sum(c for _, c in simple_errors)
    for error_type, count in simple_errors:
        percentage = (count / total_errors) * 100
        logger.info(f"  - {error_type:<25} {count:>4} 个 ({percentage:>5.1f}%)")
    
    logger.info(f"\n预计修复: {phase1_total} 个错误 ({(phase1_total/total_errors)*100:.1f}%)")
    logger.info(f"剩余错误: {total_errors - phase1_total} 个")
    
    logger.info("\n【阶段2：核心模块优先修复】（预计3-5天）")
    logger.info("优先修复重要性高的核心模块，确保基础设施稳定")
    logger.info("\n修复顺序：")
    
    core_modules = [
        (m, c) for m, c, imp, _ in module_priorities 
        if imp >= 8
    ]
    
    for i, (module, count) in enumerate(core_modules, 1):
        percentage = (count / total_errors) * 100
        logger.info(f"  {i}. {module:<40} {count:>4} 个 ({percentage:>5.1f}%)")
    
    logger.info("\n【阶段3：业务模块系统修复】（预计5-7天）")
    logger.info("修复中等重要性的业务模块")
    logger.info("\n修复顺序：")
    
    business_modules = [
        (m, c) for m, c, imp, _ in module_priorities 
        if 6 <= imp < 8
    ]
    
    for i, (module, count) in enumerate(business_modules, 1):
        percentage = (count / total_errors) * 100
        logger.info(f"  {i}. {module:<40} {count:>4} 个 ({percentage:>5.1f}%)")
    
    logger.info("\n【阶段4：automation模块修复】（预计1-2周）")
    logger.info("修复automation模块，处理第三方库类型问题")
    logger.info("\n修复顺序：")
    
    automation_modules = [
        (m, c) for m, c, imp, _ in module_priorities 
        if imp < 6
    ]
    
    for i, (module, count) in enumerate(automation_modules, 1):
        percentage = (count / total_errors) * 100
        logger.info(f"  {i}. {module:<40} {count:>4} 个 ({percentage:>5.1f}%)")
    
    logger.info("\n【阶段5：最终验证和CI集成】（预计3-5天）")
    logger.info("- 全量mypy检查确认零错误")
    logger.info("- 运行完整测试套件")
    logger.info("- 配置CI/CD集成")
    logger.info("- 配置pre-commit hook")
    logger.info("- 优化mypy性能")
    
    logger.info("\n" + "=" * 80)
    logger.info("修复策略建议")
    logger.info("=" * 80)
    
    logger.info("\n1. 批量修复工具（阶段1）：")
    logger.info("   - fix_generic_types.py: 修复 type-arg 错误")
    logger.info("   - fix_return_types.py: 修复 no-untyped-def 错误")
    logger.info("   - fix_type_annotations.py: 修复 var-annotated 错误")
    
    logger.info("\n2. Django ORM处理（阶段2-3）：")
    logger.info("   - 创建Model类型存根(.pyi文件)")
    logger.info("   - 使用cast()处理动态属性")
    logger.info("   - 为QuerySet添加泛型参数")
    
    logger.info("\n3. 第三方库处理（阶段4）：")
    logger.info("   - 配置mypy.ini的ignore_missing_imports")
    logger.info("   - 使用type: ignore注释")
    logger.info("   - 创建类型存根文件（如需要）")
    
    logger.info("\n4. 验证策略：")
    logger.info("   - 每个模块修复后运行mypy验证")
    logger.info("   - 每个阶段完成后运行测试套件")
    logger.info("   - 最终全量验证确保零错误")
    
    logger.info("\n" + "=" * 80)


def main() -> None:
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s"
    )
    
    # 读取错误分析文件
    analysis_file = Path(__file__).parent.parent / "mypy_error_analysis.txt"
    
    if not analysis_file.exists():
        logger.error(f"错误分析文件不存在: {analysis_file}")
        logger.error("请先运行 analyze_mypy_errors.py 生成错误分析")
        return
    
    logger.info(f"读取错误分析文件: {analysis_file}")
    data = parse_error_analysis(analysis_file)
    
    # 生成优先级报告
    generate_priority_report(data)
    
    # 保存报告到文件
    output_file = Path(__file__).parent.parent / "mypy_fix_priority.txt"
    
    # 重定向logger输出到文件
    file_handler = logging.FileHandler(output_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)
    
    generate_priority_report(data)
    
    logger.info(f"\n优先级报告已保存到: {output_file}")


if __name__ == "__main__":
    main()
