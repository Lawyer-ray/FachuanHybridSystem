#!/usr/bin/env python3
"""
导入路径更新脚本

扫描所有 Python 文件，查找并更新旧的导入路径为新的导入路径。

主要更新：
1. 测试文件导入路径：apps.*.tests -> tests.unit/integration/property
2. Factories 导入路径：apps.tests.factories -> tests.factories
3. Mocks 导入路径：apps.tests.mocks -> tests.mocks
4. Admin 导入路径：apps.*.admin -> apps.*.admin.*_admin
5. API 导入路径：apps.*.api -> apps.*.api.*_api
6. Services 导入路径：apps.*.services -> apps.*.services.*_service
"""

import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from apps.core.path import Path


@dataclass
class ImportUpdate:
    """导入更新记录"""

    file_path: Path
    line_number: int
    old_import: str
    new_import: str
    pattern_name: str


class ImportPathUpdater:
    """导入路径更新器"""

    def __init__(self, root_path: Path, dry_run: bool = True):
        self.root_path = root_path
        self.dry_run = dry_run
        self.updates: List[ImportUpdate] = []
        self.files_scanned = 0
        self.files_updated = 0

        # 定义导入路径更新模式
        self.import_patterns = self._define_import_patterns()

    def _define_import_patterns(self) -> List[Tuple[str, str, str]]:
        """
        定义导入路径更新模式

        Returns:
            List of (pattern_name, old_pattern, new_pattern)
        """
        return [
            # 1. 测试文件导入 - 从 apps.*.tests 到 tests.unit/integration/property
            ("test_imports", r"from apps\.(\w+)\.tests import", r"from tests.unit.\1 import"),
            ("test_imports_submodule", r"from apps\.(\w+)\.tests\.(\w+) import", r"from tests.unit.\1.\2 import"),
            ("test_imports_as", r"import apps\.(\w+)\.tests", r"import tests.unit.\1"),
            # 2. Factories 导入 - 从 apps.tests.factories 到 tests.factories
            ("factories_imports", r"from apps\.tests\.factories import", r"from tests.factories import"),
            (
                "factories_imports_submodule",
                r"from apps\.tests\.factories\.(\w+) import",
                r"from tests.factories.\1 import",
            ),
            ("factories_imports_as", r"import apps\.tests\.factories", r"import tests.factories"),
            # 3. Mocks 导入 - 从 apps.tests.mocks 到 tests.mocks
            ("mocks_imports", r"from apps\.tests\.mocks import", r"from tests.mocks import"),
            ("mocks_imports_submodule", r"from apps\.tests\.mocks\.(\w+) import", r"from tests.mocks.\1 import"),
            ("mocks_imports_as", r"import apps\.tests\.mocks", r"import tests.mocks"),
            # 4. Admin 导入 - 从 apps.*.admin 到 apps.*.admin.*_admin
            # 注意：这个需要更智能的处理，因为需要知道具体的模型名
            # 暂时保留原有导入，在后续手动调整
            # 5. API 导入 - 从 apps.*.api 到 apps.*.api.*_api
            # 注意：这个需要更智能的处理，因为需要知道具体的资源名
            # 暂时保留原有导入，在后续手动调整
            # 6. Services 导入 - 从 apps.*.services 到 apps.*.services.*_service
            # 注意：这个需要更智能的处理，因为需要知道具体的服务名
            # 暂时保留原有导入，在后续手动调整
        ]

    def scan_python_files(self) -> List[Path]:
        """
        扫描所有 Python 文件

        Returns:
            Python 文件路径列表
        """
        print("扫描 Python 文件...")

        python_files = []

        # 扫描 apps/ 目录
        apps_dir = self.root_path / "apps"
        if apps_dir.exists():
            python_files.extend(apps_dir.rglob("*.py"))

        # 扫描 tests/ 目录
        tests_dir = self.root_path / "tests"
        if tests_dir.exists():
            python_files.extend(tests_dir.rglob("*.py"))

        # 扫描 scripts/ 目录
        scripts_dir = self.root_path / "scripts"
        if scripts_dir.exists():
            python_files.extend(scripts_dir.rglob("*.py"))

        # 过滤掉迁移文件和 __pycache__
        python_files = [
            f
            for f in python_files
            if "__pycache__" not in str(f)
            and "migrations" not in str(f)
            and ".hypothesis" not in str(f)
            and ".mypy_cache" not in str(f)
            and ".pytest_cache" not in str(f)
        ]

        print(f"找到 {len(python_files)} 个 Python 文件")
        return python_files

    def analyze_file(self, file_path: Path) -> List[ImportUpdate]:
        """
        分析单个文件的导入路径

        Args:
            file_path: 文件路径

        Returns:
            该文件的导入更新列表
        """
        updates = []

        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                # 跳过注释行
                if line.strip().startswith("#"):
                    continue

                # 检查每个导入模式
                for pattern_name, old_pattern, new_pattern in self.import_patterns:
                    match = re.search(old_pattern, line)
                    if match:
                        # 生成新的导入语句
                        new_line = re.sub(old_pattern, new_pattern, line)

                        updates.append(
                            ImportUpdate(
                                file_path=file_path,
                                line_number=line_num,
                                old_import=line.strip(),
                                new_import=new_line.strip(),
                                pattern_name=pattern_name,
                            )
                        )

        except Exception as e:
            print(f"⚠️  无法读取文件 {file_path}: {e}")

        return updates

    def scan_all_files(self) -> None:
        """扫描所有文件并收集导入更新"""
        python_files = self.scan_python_files()

        print("\n分析导入路径...")
        for file_path in python_files:
            self.files_scanned += 1
            file_updates = self.analyze_file(file_path)
            self.updates.extend(file_updates)

        print(f"扫描完成: {self.files_scanned} 个文件")
        print(f"找到 {len(self.updates)} 处需要更新的导入")

    def group_updates_by_file(self) -> Dict[Path, List[ImportUpdate]]:
        """按文件分组更新"""
        grouped = {}
        for update in self.updates:
            if update.file_path not in grouped:
                grouped[update.file_path] = []
            grouped[update.file_path].append(update)
        return grouped

    def display_updates(self) -> None:
        """显示所有更新"""
        if not self.updates:
            print("\n✅ 没有需要更新的导入路径")
            return

        print(f"\n{'=' * 80}")
        print(f"导入路径更新预览 ({len(self.updates)} 处更新)")
        print(f"{'=' * 80}\n")

        grouped = self.group_updates_by_file()

        for file_path, file_updates in sorted(grouped.items()):
            print(f"\n📄 {file_path.relative_to(self.root_path)}")
            print(f"   {len(file_updates)} 处更新")

            for update in file_updates:
                print(f"\n   行 {update.line_number} [{update.pattern_name}]:")
                print(f"   - {update.old_import}")
                print(f"   + {update.new_import}")

        print(f"\n{'=' * 80}")
        print(f"总计: {len(grouped)} 个文件, {len(self.updates)} 处更新")
        print(f"{'=' * 80}\n")

    def apply_updates(self) -> None:
        """应用所有更新"""
        if not self.updates:
            print("\n✅ 没有需要更新的导入路径")
            return

        if self.dry_run:
            print("\n[DRY RUN] 将更新以下文件:")
            self.display_updates()
            return

        print("\n应用导入路径更新...")

        grouped = self.group_updates_by_file()

        for file_path, file_updates in grouped.items():
            try:
                # 读取文件内容
                content = file_path.read_text(encoding="utf-8")
                lines = content.split("\n")

                # 按行号倒序排序，避免行号偏移
                file_updates.sort(key=lambda u: u.line_number, reverse=True)

                # 应用更新
                for update in file_updates:
                    line_idx = update.line_number - 1
                    if line_idx < len(lines):
                        # 替换整行
                        old_line = lines[line_idx]
                        for pattern_name, old_pattern, new_pattern in self.import_patterns:
                            if pattern_name == update.pattern_name:
                                lines[line_idx] = re.sub(old_pattern, new_pattern, old_line)
                                break

                # 写回文件
                new_content = "\n".join(lines)
                file_path.write_text(new_content, encoding="utf-8")

                self.files_updated += 1
                print(f"✓ 更新 {file_path.relative_to(self.root_path)} ({len(file_updates)} 处)")

            except Exception as e:
                print(f"❌ 更新失败 {file_path}: {e}")

        print(f"\n✅ 成功更新 {self.files_updated} 个文件")

    def verify_imports(self) -> bool:
        """
        验证更新后的导入路径是否正确

        Returns:
            是否所有导入都有效
        """
        print("\n验证导入路径...")

        # 这里可以尝试导入每个模块来验证
        # 但由于可能有依赖问题，我们只做基本的语法检查

        python_files = self.scan_python_files()
        errors = []

        for file_path in python_files:
            try:
                # 尝试编译文件以检查语法
                content = file_path.read_text(encoding="utf-8")
                compile(content, str(file_path), "exec")
            except SyntaxError as e:
                errors.append((file_path, str(e)))

        if errors:
            print(f"\n❌ 发现 {len(errors)} 个语法错误:")
            for file_path, error in errors:
                print(f"   {file_path.relative_to(self.root_path)}: {error}")
            return False

        print(f"✅ 所有文件语法正确")
        return True

    def generate_report(self) -> None:
        """生成更新报告"""
        report_path = self.root_path / "scripts" / "refactoring" / "import_update_report.md"

        print(f"\n生成更新报告: {report_path}")

        grouped = self.group_updates_by_file()

        report_lines = [
            "# 导入路径更新报告",
            "",
            f"生成时间: {self._get_timestamp()}",
            "",
            "## 统计信息",
            "",
            f"- 扫描文件数: {self.files_scanned}",
            f"- 更新文件数: {len(grouped)}",
            f"- 更新总数: {len(self.updates)}",
            "",
            "## 更新模式统计",
            "",
        ]

        # 统计每种模式的更新次数
        pattern_counts = {}
        for update in self.updates:
            pattern_counts[update.pattern_name] = pattern_counts.get(update.pattern_name, 0) + 1

        for pattern_name, count in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True):
            report_lines.append(f"- {pattern_name}: {count} 处")

        report_lines.extend(["", "## 详细更新列表", ""])

        for file_path, file_updates in sorted(grouped.items()):
            report_lines.append(f"### {file_path.relative_to(self.root_path)}")
            report_lines.append("")
            report_lines.append(f"更新数: {len(file_updates)}")
            report_lines.append("")

            for update in file_updates:
                report_lines.extend(
                    [
                        f"**行 {update.line_number}** [{update.pattern_name}]",
                        "",
                        "```python",
                        f"# 旧:",
                        update.old_import,
                        f"# 新:",
                        update.new_import,
                        "```",
                        "",
                    ]
                )

        report_content = "\n".join(report_lines)
        report_path.write_text(report_content, encoding="utf-8")

        print(f"✅ 报告已生成")

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def run(self) -> None:
        """运行导入路径更新"""
        print("=" * 80)
        print("导入路径更新脚本")
        print("=" * 80)
        print(f"模式: {'DRY RUN' if self.dry_run else 'EXECUTE'}")
        print(f"根目录: {self.root_path}")
        print("=" * 80)
        print()

        # 1. 扫描所有文件
        self.scan_all_files()

        # 2. 显示更新预览
        self.display_updates()

        # 3. 应用更新
        if self.updates:
            self.apply_updates()

            # 4. 验证导入
            if not self.dry_run:
                self.verify_imports()

            # 5. 生成报告
            self.generate_report()

        # 6. 显示总结
        print("\n" + "=" * 80)
        if self.dry_run:
            print("✅ Dry-run 完成！使用 --execute 参数执行实际更新。")
        else:
            print(f"✅ 更新完成！")
            print(f"   - 扫描文件: {self.files_scanned}")
            print(f"   - 更新文件: {self.files_updated}")
            print(f"   - 更新总数: {len(self.updates)}")
        print("=" * 80)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="更新 Python 文件中的导入路径",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Dry-run 模式（默认）
  python update_imports.py

  # 执行实际更新
  python update_imports.py --execute

  # 只显示统计信息
  python update_imports.py --stats-only
        """,
    )

    parser.add_argument("--execute", action="store_true", help="执行实际更新（默认为 dry-run）")

    parser.add_argument("--stats-only", action="store_true", help="只显示统计信息，不显示详细更新")

    args = parser.parse_args()

    # 获取项目根目录
    script_dir = Path(__file__).parent
    root_path = script_dir.parent.parent

    try:
        # 创建更新器
        updater = ImportPathUpdater(root_path=root_path, dry_run=not args.execute)

        # 运行更新
        updater.run()

    except KeyboardInterrupt:
        print("\n\n⚠️  操作已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 更新失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
