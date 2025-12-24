#!/usr/bin/env python3
"""
脚本文件迁移工具

将脚本文件按功能分类迁移到对应的子目录：
- testing/: 测试相关脚本
- development/: 开发工具脚本
- automation/: 自动化脚本
"""

from pathlib import Path
import shutil
from typing import List, Tuple


class ScriptMigrator:
    """脚本迁移器"""
    
    def __init__(self, scripts_dir: Path):
        self.scripts_dir = scripts_dir
        self.migrations: List[Tuple[Path, Path]] = []
    
    def plan_migrations(self) -> None:
        """规划迁移任务"""
        # 测试相关脚本 (test_*.py)
        test_scripts = [
            'test_admin_login.py',
            'test_company_list.py',
            'test_full_quote_flow.py',
            'test_premium_from_client.py',
            'test_quote_with_service.py',
        ]
        
        for script in test_scripts:
            source = self.scripts_dir / script
            if source.exists():
                dest = self.scripts_dir / 'testing' / script
                self.migrations.append((source, dest))
        
        # 开发工具脚本 (check_*.py, debug_*.py, example_*.py, quick_*.py)
        dev_scripts = [
            'check_admin_config.py',
            'debug_token_capture.py',
            'example_use_token.py',
            'quick_test.py',
        ]
        
        for script in dev_scripts:
            source = self.scripts_dir / script
            if source.exists():
                dest = self.scripts_dir / 'development' / script
                self.migrations.append((source, dest))
        
        # 自动化脚本 (court_*.js)
        automation_scripts = [
            'court_captcha_userscript.js',
        ]
        
        for script in automation_scripts:
            source = self.scripts_dir / script
            if source.exists():
                dest = self.scripts_dir / 'automation' / script
                self.migrations.append((source, dest))
    
    def execute(self, dry_run: bool = True) -> None:
        """执行迁移"""
        if not self.migrations:
            self.plan_migrations()
        
        print(f"{'[DRY RUN] ' if dry_run else ''}脚本迁移计划:")
        print(f"总共 {len(self.migrations)} 个文件需要迁移\n")
        
        for source, dest in self.migrations:
            print(f"{'[DRY RUN] ' if dry_run else ''}移动: {source.name}")
            print(f"  从: {source.relative_to(self.scripts_dir.parent)}")
            print(f"  到: {dest.relative_to(self.scripts_dir.parent)}")
            
            if not dry_run:
                # 确保目标目录存在
                dest.parent.mkdir(parents=True, exist_ok=True)
                
                # 移动文件
                shutil.move(str(source), str(dest))
                print(f"  ✓ 完成")
            
            print()
        
        if dry_run:
            print("\n这是 dry-run 模式，没有实际移动文件")
            print("运行 python migrate_scripts.py --execute 来执行迁移")
        else:
            print(f"\n✓ 成功迁移 {len(self.migrations)} 个脚本文件")


def main():
    """主函数"""
    import sys
    
    # 获取 scripts 目录
    scripts_dir = Path(__file__).parent.parent
    
    # 创建迁移器
    migrator = ScriptMigrator(scripts_dir)
    
    # 检查是否是执行模式
    dry_run = '--execute' not in sys.argv
    
    # 执行迁移
    migrator.execute(dry_run=dry_run)


if __name__ == '__main__':
    main()
