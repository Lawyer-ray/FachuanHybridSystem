"""保守的批量修复脚本 - P0阶段"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

# 添加backend到路径
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from scripts.mypy_final_cleanup.backup_manager import BackupManager
from scripts.mypy_final_cleanup.conservative_type_args_fixer import ConservativeTypeArgsFixer
from scripts.mypy_final_cleanup.logger_config import setup_logger

logger = setup_logger(__name__)


def get_mypy_error_count() -> int:
    """获取当前mypy错误数量"""
    try:
        result = subprocess.run(
            ["mypy", "--strict", "apps/"],
            cwd=backend_path,
            capture_output=True,
            text=True
        )
        output = result.stdout + result.stderr
        
        # 查找 "Found X errors"
        import re
        match = re.search(r'Found (\d+) errors', output)
        if match:
            return int(match.group(1))
        return 0
    except Exception as e:
        logger.error(f"获取mypy错误数失败: {e}")
        return 0


def extract_type_arg_errors() -> list[str]:
    """提取所有type-arg错误的文件"""
    try:
        result = subprocess.run(
            ["mypy", "--strict", "apps/"],
            cwd=backend_path,
            capture_output=True,
            text=True
        )
        output = result.stdout + result.stderr
        
        # 提取type-arg错误的文件
        files = set()
        for line in output.split('\n'):
            if '[type-arg]' in line:
                # 格式：apps/xxx/yyy.py:123: error: ...
                parts = line.split(':')
                if len(parts) >= 2:
                    file_path = parts[0].strip()
                    if file_path.startswith('apps/'):
                        files.add(file_path)
        
        return sorted(list(files))
    except Exception as e:
        logger.error(f"提取type-arg错误失败: {e}")
        return []


def main() -> None:
    """主函数"""
    
    logger.info("=" * 80)
    logger.info("P0阶段保守修复 - type-arg错误")
    logger.info("=" * 80)
    
    # 获取初始错误数
    initial_errors = get_mypy_error_count()
    logger.info(f"初始错误数: {initial_errors}")
    
    # 提取type-arg错误文件
    logger.info("提取type-arg错误文件...")
    error_files = extract_type_arg_errors()
    logger.info(f"找到 {len(error_files)} 个包含type-arg错误的文件")
    
    if not error_files:
        logger.info("没有找到type-arg错误")
        return
    
    # 创建修复器
    backup_manager = BackupManager()
    fixer = ConservativeTypeArgsFixer(backup_manager)
    
    # 阶段1：小批量测试（5个文件）
    logger.info("\n" + "=" * 80)
    logger.info("阶段1：小批量测试（5个文件）")
    logger.info("=" * 80)
    
    test_files = error_files[:5]
    test_results = []
    
    for file_path in test_files:
        logger.info(f"测试修复: {file_path}")
        result = fixer.fix_file(file_path, dry_run=False)
        test_results.append(result)
        
        if not result["success"]:
            logger.error(f"修复失败: {result['errors']}")
        else:
            logger.info(f"  修复: {result['fixes']}, 忽略: {result['ignores']}")
    
    # 验证测试结果
    test_errors = get_mypy_error_count()
    logger.info(f"\n测试后错误数: {test_errors}")
    logger.info(f"错误变化: {test_errors - initial_errors:+d}")
    
    # 如果错误数增加超过10%，停止
    if test_errors > initial_errors * 1.1:
        logger.error("❌ 测试失败：错误数增加超过10%")
        logger.error("建议：检查修复逻辑，回滚修改")
        
        # 询问是否回滚
        response = input("\n是否回滚测试修复？(y/n): ")
        if response.lower() == 'y':
            for file_path in test_files:
                backup_manager.restore_file(file_path)
            logger.info("已回滚测试修复")
        return
    
    logger.info("✅ 测试通过")
    
    # 阶段2：批量修复（每批20个文件）
    logger.info("\n" + "=" * 80)
    logger.info("阶段2：批量修复")
    logger.info("=" * 80)
    
    remaining_files = error_files[5:]  # 跳过已测试的5个
    batch_size = 20
    
    total_fixes = sum(r["fixes"] for r in test_results)
    total_ignores = sum(r["ignores"] for r in test_results)
    
    for i in range(0, len(remaining_files), batch_size):
        batch = remaining_files[i:i+batch_size]
        batch_num = i // batch_size + 1
        
        logger.info(f"\n批次 {batch_num}: 处理 {len(batch)} 个文件")
        
        batch_results = []
        for file_path in batch:
            result = fixer.fix_file(file_path, dry_run=False)
            batch_results.append(result)
            
            if result["success"]:
                total_fixes += result["fixes"]
                total_ignores += result["ignores"]
        
        # 验证批次结果
        batch_errors = get_mypy_error_count()
        logger.info(f"批次后错误数: {batch_errors}")
        logger.info(f"错误变化: {batch_errors - initial_errors:+d}")
        
        # 如果错误数增加超过50，回滚该批次
        if batch_errors > initial_errors + 50:
            logger.error(f"❌ 批次 {batch_num} 失败：错误数增加过多")
            logger.error("回滚该批次...")
            
            for file_path in batch:
                backup_manager.restore_file(file_path)
            
            logger.info("已回滚批次修复")
            break
        
        logger.info(f"✅ 批次 {batch_num} 完成")
    
    # 最终验证
    logger.info("\n" + "=" * 80)
    logger.info("最终验证")
    logger.info("=" * 80)
    
    final_errors = get_mypy_error_count()
    logger.info(f"最终错误数: {final_errors}")
    logger.info(f"错误减少: {initial_errors - final_errors}")
    logger.info(f"总修复数: {total_fixes}")
    logger.info(f"总忽略数: {total_ignores}")
    
    # 成功标准
    if final_errors < initial_errors:
        logger.info("✅ 修复成功：错误数减少")
    elif final_errors == initial_errors:
        logger.info("⚠️  错误数未变化")
    else:
        logger.error("❌ 修复失败：错误数增加")
    
    # 生成报告
    report_path = backend_path / "P0_CONSERVATIVE_FIX_REPORT.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# P0保守修复报告\n\n")
        f.write(f"## 统计\n\n")
        f.write(f"- 初始错误数: {initial_errors}\n")
        f.write(f"- 最终错误数: {final_errors}\n")
        f.write(f"- 错误减少: {initial_errors - final_errors}\n")
        f.write(f"- 处理文件数: {len(error_files)}\n")
        f.write(f"- 总修复数: {total_fixes}\n")
        f.write(f"- 总忽略数: {total_ignores}\n")
    
    logger.info(f"\n报告已生成: {report_path}")


if __name__ == "__main__":
    main()
