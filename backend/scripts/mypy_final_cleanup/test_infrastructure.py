"""测试基础设施组件"""

from __future__ import annotations

from pathlib import Path

from .backup_manager import BackupManager
from .error_analyzer import ErrorAnalyzer, ErrorInfo
from .logger_config import setup_logger


def test_error_analyzer() -> None:
    """测试ErrorAnalyzer"""
    logger = setup_logger("test_error_analyzer")
    logger.info("开始测试ErrorAnalyzer")
    
    analyzer = ErrorAnalyzer()
    
    # 创建测试数据
    test_errors = {
        "type-arg": [
            ErrorInfo("apps/cases/models.py", 10, "type-arg", "List needs type params", ""),
            ErrorInfo("apps/cases/models.py", 20, "type-arg", "Dict needs type params", ""),
        ],
        "attr-defined": [
            ErrorInfo("apps/cases/views.py", 30, "attr-defined", "No attribute 'objects'", ""),
        ],
        "no-untyped-def": [
            ErrorInfo("apps/cases/services.py", 40, "no-untyped-def", "Function missing type", ""),
        ],
    }
    
    # 测试生成优先级报告
    report = analyzer.generate_priority_report(test_errors)
    logger.info(f"优先级报告:\n{report}")
    
    # 测试获取可修复错误
    type_arg_errors = analyzer.get_fixable_errors("type-arg", test_errors)
    logger.info(f"type-arg错误数量: {len(type_arg_errors)}")
    
    logger.info("ErrorAnalyzer测试完成")


def test_backup_manager() -> None:
    """测试BackupManager"""
    logger = setup_logger("test_backup_manager")
    logger.info("开始测试BackupManager")
    
    backend_path = Path(__file__).parent.parent.parent
    manager = BackupManager(backend_path)
    
    # 创建测试文件
    test_file = "test_backup_file.txt"
    test_path = backend_path / test_file
    test_path.write_text("Original content", encoding="utf-8")
    
    try:
        # 测试备份
        backup_path = manager.backup_file(test_file)
        if backup_path:
            logger.info(f"备份成功: {backup_path}")
        else:
            logger.error("备份失败")
            return
        
        # 修改原文件
        test_path.write_text("Modified content", encoding="utf-8")
        logger.info("已修改原文件")
        
        # 测试恢复
        if manager.restore_file(test_file):
            logger.info("恢复成功")
            content = test_path.read_text(encoding="utf-8")
            logger.info(f"恢复后的内容: {content}")
        else:
            logger.error("恢复失败")
        
        # 测试列出备份
        backups = manager.list_backups()
        logger.info(f"备份列表: {backups}")
        
    finally:
        # 清理测试文件
        if test_path.exists():
            test_path.unlink()
        manager.clear_backups()
    
    logger.info("BackupManager测试完成")


def main() -> None:
    """运行所有测试"""
    logger = setup_logger("test_infrastructure")
    logger.info("=" * 60)
    logger.info("开始测试基础设施组件")
    logger.info("=" * 60)
    
    test_error_analyzer()
    logger.info("")
    
    test_backup_manager()
    logger.info("")
    
    logger.info("=" * 60)
    logger.info("所有测试完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
