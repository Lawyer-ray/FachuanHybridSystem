#!/usr/bin/env python3
"""
测试文件迁移脚本

将分散在各个 app 中的测试文件迁移到集中的 tests/ 目录
"""

import os
import re
import shutil
from pathlib import Path
from typing import List, Dict, Tuple


class TestFileMigrator:
    """测试文件迁移器"""
    
    def __init__(self, root_path: Path, dry_run: bool = True):
        self.root_path = root_path
        self.dry_run = dry_run
        self.migrations: List[Tuple[Path, Path]] = []
        self.import_updates: Dict[Path, List[Tuple[str, str]]] = {}
    
    def scan_test_files(self) -> None:
        """扫描所有测试文件"""
        print("扫描测试文件...")
        
        # 扫描 apps/*/tests/ 目录
        apps_path = self.root_path / "apps"
        for app_dir in apps_path.iterdir():
            if not app_dir.is_dir() or app_dir.name == "tests":
                continue
            
            tests_dir = app_dir / "tests"
            if tests_dir.exists() and tests_dir.is_dir():
                self._scan_app_tests(app_dir.name, tests_dir)
        
        # 扫描 apps/tests/ 目录
        apps_tests_dir = apps_path / "tests"
        if apps_tests_dir.exists():
            self._scan_apps_tests(apps_tests_dir)
        
        print(f"找到 {len(self.migrations)} 个测试文件需要迁移")
    
    def _scan_app_tests(self, app_name: str, tests_dir: Path) -> None:
        """扫描单个 app 的测试目录"""
        for test_file in tests_dir.rglob("test*.py"):
            if test_file.is_file():
                # 确定目标目录
                target_dir = self._determine_target_dir(test_file)
                
                # 构建目标路径
                relative_path = test_file.relative_to(tests_dir)
                target_path = self.root_path / "tests" / target_dir / app_name / relative_path
                
                self.migrations.append((test_file, target_path))
    
    def _scan_apps_tests(self, apps_tests_dir: Path) -> None:
        """扫描 apps/tests/ 目录"""
        # 迁移 factories/
        factories_dir = apps_tests_dir / "factories"
        if factories_dir.exists():
            target_dir = self.root_path / "tests" / "factories"
            for factory_file in factories_dir.rglob("*.py"):
                if factory_file.is_file():
                    relative_path = factory_file.relative_to(factories_dir)
                    target_path = target_dir / relative_path
                    self.migrations.append((factory_file, target_path))
        
        # 迁移 mocks/
        mocks_dir = apps_tests_dir / "mocks"
        if mocks_dir.exists():
            target_dir = self.root_path / "tests" / "mocks"
            for mock_file in mocks_dir.rglob("*.py"):
                if mock_file.is_file():
                    relative_path = mock_file.relative_to(mocks_dir)
                    target_path = target_dir / relative_path
                    self.migrations.append((mock_file, target_path))
        
        # 迁移其他测试文件
        for test_file in apps_tests_dir.glob("test*.py"):
            if test_file.is_file():
                target_dir = self._determine_target_dir(test_file)
                target_path = self.root_path / "tests" / target_dir / test_file.name
                self.migrations.append((test_file, target_path))
    
    def _determine_target_dir(self, test_file: Path) -> str:
        """确定测试文件的目标目录"""
        file_name = test_file.name
        
        # API 测试 -> integration/
        if "_api" in file_name or "api_" in file_name:
            return "integration"
        
        # Property-based 测试 -> property/
        if "_properties" in file_name or "properties_" in file_name:
            return "property"
        
        # 默认 -> unit/
        return "unit"
    
    def execute_migrations(self) -> None:
        """执行迁移"""
        print("\n开始迁移测试文件...")
        
        for source, target in self.migrations:
            if self.dry_run:
                print(f"[DRY RUN] {source} -> {target}")
            else:
                # 创建目标目录
                target.parent.mkdir(parents=True, exist_ok=True)
                
                # 移动文件
                shutil.copy2(source, target)
                print(f"✓ {source} -> {target}")
                
                # 分析导入路径
                self._analyze_imports(target)
    
    def _analyze_imports(self, file_path: Path) -> None:
        """分析文件中的导入路径"""
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # 查找需要更新的导入
            import_patterns = [
                # from apps.xxx.tests import ...
                (r'from apps\.(\w+)\.tests import', r'from tests.unit.\1 import'),
                (r'from apps\.(\w+)\.tests\.', r'from tests.unit.\1.'),
                
                # from apps.tests.factories import ...
                (r'from apps\.tests\.factories import', r'from tests.factories import'),
                (r'from apps\.tests\.factories\.', r'from tests.factories.'),
                
                # from apps.tests.mocks import ...
                (r'from apps\.tests\.mocks import', r'from tests.mocks import'),
                (r'from apps\.tests\.mocks\.', r'from tests.mocks.'),
            ]
            
            updates = []
            for old_pattern, new_pattern in import_patterns:
                if re.search(old_pattern, content):
                    updates.append((old_pattern, new_pattern))
            
            if updates:
                self.import_updates[file_path] = updates
        
        except Exception as e:
            print(f"警告: 无法分析 {file_path}: {e}")
    
    def update_imports(self) -> None:
        """更新导入路径"""
        if not self.import_updates:
            print("\n没有需要更新的导入路径")
            return
        
        print(f"\n更新 {len(self.import_updates)} 个文件的导入路径...")
        
        for file_path, updates in self.import_updates.items():
            if self.dry_run:
                print(f"[DRY RUN] 更新 {file_path}")
                for old_pattern, new_pattern in updates:
                    print(f"  {old_pattern} -> {new_pattern}")
            else:
                try:
                    content = file_path.read_text(encoding='utf-8')
                    
                    for old_pattern, new_pattern in updates:
                        content = re.sub(old_pattern, new_pattern, content)
                    
                    file_path.write_text(content, encoding='utf-8')
                    print(f"✓ 更新 {file_path}")
                
                except Exception as e:
                    print(f"错误: 无法更新 {file_path}: {e}")
    
    def cleanup_old_files(self) -> None:
        """清理旧的测试文件"""
        if self.dry_run:
            print("\n[DRY RUN] 将删除以下文件:")
            for source, _ in self.migrations:
                print(f"  {source}")
            return
        
        print("\n清理旧的测试文件...")
        for source, _ in self.migrations:
            try:
                if source.exists():
                    source.unlink()
                    print(f"✓ 删除 {source}")
            except Exception as e:
                print(f"错误: 无法删除 {source}: {e}")
        
        # 删除空目录
        self._cleanup_empty_dirs()
    
    def _cleanup_empty_dirs(self) -> None:
        """清理空目录"""
        apps_path = self.root_path / "apps"
        
        for app_dir in apps_path.iterdir():
            if not app_dir.is_dir():
                continue
            
            tests_dir = app_dir / "tests"
            if tests_dir.exists() and tests_dir.is_dir():
                # 检查是否为空
                if not any(tests_dir.iterdir()):
                    try:
                        tests_dir.rmdir()
                        print(f"✓ 删除空目录 {tests_dir}")
                    except Exception as e:
                        print(f"警告: 无法删除 {tests_dir}: {e}")
    
    def run(self) -> None:
        """运行迁移"""
        self.scan_test_files()
        self.execute_migrations()
        self.update_imports()
        
        if not self.dry_run:
            self.cleanup_old_files()
        
        print("\n迁移完成!")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="迁移测试文件到集中的 tests/ 目录")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示将要执行的操作，不实际执行"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行迁移"
    )
    
    args = parser.parse_args()
    
    # 获取项目根目录
    script_dir = Path(__file__).parent
    root_path = script_dir.parent.parent
    
    # 创建迁移器
    migrator = TestFileMigrator(
        root_path=root_path,
        dry_run=not args.execute
    )
    
    # 运行迁移
    migrator.run()
    
    if not args.execute:
        print("\n提示: 使用 --execute 参数实际执行迁移")


if __name__ == "__main__":
    main()
