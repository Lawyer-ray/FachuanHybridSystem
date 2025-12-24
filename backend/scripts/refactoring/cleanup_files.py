"""
清理重复和无用文件

删除以下文件和目录：
1. backend/backend/ 目录（重复的 Django 项目目录）
2. apps/*/tests.py 文件（已迁移到 tests/ 目录）
3. apps/*/admin.py 文件（已拆分到 admin/ 目录）
4. apps/*/api.py 文件（已拆分到 api/ 目录）
"""

import shutil
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def cleanup_duplicate_backend_directory():
    """删除重复的 backend/backend/ 目录"""
    backend_backend_dir = project_root / "backend"
    
    if backend_backend_dir.exists() and backend_backend_dir.is_dir():
        print(f"删除重复的目录: {backend_backend_dir}")
        shutil.rmtree(backend_backend_dir)
        print("✓ 已删除 backend/backend/ 目录")
    else:
        print("✗ backend/backend/ 目录不存在，跳过")


def cleanup_tests_py_files():
    """删除 apps/*/tests.py 文件"""
    apps_dir = project_root / "apps"
    deleted_files = []
    
    for app_dir in apps_dir.iterdir():
        if app_dir.is_dir() and not app_dir.name.startswith('.'):
            tests_file = app_dir / "tests.py"
            if tests_file.exists():
                print(f"删除测试文件: {tests_file}")
                tests_file.unlink()
                deleted_files.append(str(tests_file.relative_to(project_root)))
    
    if deleted_files:
        print(f"✓ 已删除 {len(deleted_files)} 个 tests.py 文件:")
        for file in deleted_files:
            print(f"  - {file}")
    else:
        print("✗ 没有找到需要删除的 tests.py 文件")


def cleanup_admin_py_files():
    """删除 apps/*/admin.py 文件（如果已经有 admin/ 目录）"""
    apps_dir = project_root / "apps"
    deleted_files = []
    
    for app_dir in apps_dir.iterdir():
        if app_dir.is_dir() and not app_dir.name.startswith('.'):
            admin_file = app_dir / "admin.py"
            admin_dir = app_dir / "admin"
            
            # 只有当 admin/ 目录存在时才删除 admin.py
            if admin_file.exists() and admin_dir.exists() and admin_dir.is_dir():
                print(f"删除 admin 文件: {admin_file}")
                admin_file.unlink()
                deleted_files.append(str(admin_file.relative_to(project_root)))
    
    if deleted_files:
        print(f"✓ 已删除 {len(deleted_files)} 个 admin.py 文件:")
        for file in deleted_files:
            print(f"  - {file}")
    else:
        print("✗ 没有找到需要删除的 admin.py 文件")


def cleanup_api_py_files():
    """删除 apps/*/api.py 文件（如果已经有 api/ 目录）"""
    apps_dir = project_root / "apps"
    deleted_files = []
    
    for app_dir in apps_dir.iterdir():
        if app_dir.is_dir() and not app_dir.name.startswith('.'):
            api_file = app_dir / "api.py"
            api_dir = app_dir / "api"
            
            # 只有当 api/ 目录存在时才删除 api.py
            if api_file.exists() and api_dir.exists() and api_dir.is_dir():
                print(f"删除 API 文件: {api_file}")
                api_file.unlink()
                deleted_files.append(str(api_file.relative_to(project_root)))
    
    if deleted_files:
        print(f"✓ 已删除 {len(deleted_files)} 个 api.py 文件:")
        for file in deleted_files:
            print(f"  - {file}")
    else:
        print("✗ 没有找到需要删除的 api.py 文件")


def verify_gitignore():
    """验证 .gitignore 包含必要的模式"""
    gitignore_path = project_root.parent / ".gitignore"
    
    if not gitignore_path.exists():
        print("⚠ 警告: .gitignore 文件不存在")
        return
    
    gitignore_content = gitignore_path.read_text()
    
    required_patterns = [
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
        ".mypy_cache",
        ".hypothesis",
        ".coverage",
        "htmlcov",
        "*.log",
        "logs/",
        "db.sqlite3",
        ".DS_Store",
    ]
    
    missing_patterns = []
    for pattern in required_patterns:
        if pattern not in gitignore_content:
            missing_patterns.append(pattern)
    
    if missing_patterns:
        print("⚠ 警告: .gitignore 缺少以下模式:")
        for pattern in missing_patterns:
            print(f"  - {pattern}")
    else:
        print("✓ .gitignore 包含所有必要的模式")


def main():
    """主函数"""
    print("=" * 60)
    print("清理重复和无用文件")
    print("=" * 60)
    print()
    
    # 1. 删除重复的 backend/backend/ 目录
    print("1. 删除重复的 backend/backend/ 目录")
    print("-" * 60)
    cleanup_duplicate_backend_directory()
    print()
    
    # 2. 删除 apps/*/tests.py 文件
    print("2. 删除 apps/*/tests.py 文件")
    print("-" * 60)
    cleanup_tests_py_files()
    print()
    
    # 3. 删除 apps/*/admin.py 文件
    print("3. 删除 apps/*/admin.py 文件")
    print("-" * 60)
    cleanup_admin_py_files()
    print()
    
    # 4. 删除 apps/*/api.py 文件
    print("4. 删除 apps/*/api.py 文件")
    print("-" * 60)
    cleanup_api_py_files()
    print()
    
    # 5. 验证 .gitignore
    print("5. 验证 .gitignore")
    print("-" * 60)
    verify_gitignore()
    print()
    
    print("=" * 60)
    print("清理完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
