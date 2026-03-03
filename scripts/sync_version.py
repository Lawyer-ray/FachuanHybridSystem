#!/usr/bin/env python3
"""
版本号同步脚本

从 CHANGELOG.md 提取最新版本号，同步到 README.md
"""
import re
import sys
from pathlib import Path


def get_latest_version_from_changelog(changelog_path: Path) -> str | None:
    """从 CHANGELOG.md 提取最新版本号"""
    content = changelog_path.read_text(encoding="utf-8")
    # 匹配 ## [版本号] - 日期 格式
    match = re.search(r"##\s*\[(\d+\.\d+\.\d+)\]", content)
    if match:
        return match.group(1)
    return None


def update_readme_version(readme_path: Path, version: str) -> bool:
    """更新 README.md 中的版本号"""
    content = readme_path.read_text(encoding="utf-8")
    # 匹配 # 法穿AI案件管理系统V版本号
    pattern = r"(# 法穿AI案件管理系统V)\d+\.\d+(?:\.\d+)?"
    new_content = re.sub(pattern, rf"\g<1>{version}", content)

    if new_content != content:
        readme_path.write_text(new_content, encoding="utf-8")
        return True
    return False


def main() -> int:
    """主函数"""
    root = Path(__file__).parent.parent
    changelog_path = root / "CHANGELOG.md"
    readme_path = root / "README.md"

    if not changelog_path.exists():
        print(f"❌ 找不到 {changelog_path}")
        return 1

    if not readme_path.exists():
        print(f"❌ 找不到 {readme_path}")
        return 1

    # 提取最新版本号
    version = get_latest_version_from_changelog(changelog_path)
    if not version:
        print("❌ 无法从 CHANGELOG.md 提取版本号")
        return 1

    print(f"📌 CHANGELOG.md 最新版本: {version}")

    # 更新 README.md
    if update_readme_version(readme_path, version):
        print(f"✅ README.md 版本号已更新为 V{version}")
        return 0
    else:
        print(f"ℹ️  README.md 版本号已是 V{version}，无需更新")
        return 0


if __name__ == "__main__":
    sys.exit(main())
