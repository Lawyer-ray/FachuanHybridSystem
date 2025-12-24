"""
项目结构验证工具

用于验证 Django 后端项目是否符合标准结构规范
"""

from pathlib import Path
from typing import List, Set, Dict
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    def __str__(self) -> str:
        """格式化输出验证结果"""
        if self.is_valid:
            return "✅ 验证通过"
        
        result = ["❌ 验证失败\n"]
        
        if self.errors:
            result.append("错误:")
            for error in self.errors:
                result.append(f"  - {error}")
        
        if self.warnings:
            result.append("\n警告:")
            for warning in self.warnings:
                result.append(f"  - {warning}")
        
        return "\n".join(result)


class ProjectStructureValidator:
    """项目结构验证器"""
    
    def __init__(self, root_path: Path):
        """
        初始化验证器
        
        Args:
            root_path: 项目根目录路径
        """
        self.root_path = root_path
    
    def validate_all(self) -> ValidationResult:
        """
        验证所有结构
        
        Returns:
            验证结果
        """
        errors = []
        warnings = []
        
        # 验证根目录
        root_errors = self.validate_root_directory()
        errors.extend(root_errors)
        
        # 验证测试目录
        test_errors = self.validate_test_structure()
        errors.extend(test_errors)
        
        # 验证文档目录
        docs_errors = self.validate_docs_structure()
        errors.extend(docs_errors)
        
        # 验证所有 Django app
        apps_path = self.root_path / "apps"
        if apps_path.exists():
            for app_dir in apps_path.iterdir():
                if app_dir.is_dir() and not app_dir.name.startswith('.'):
                    app_errors = self.validate_app_structure(app_dir.name)
                    if app_errors:
                        errors.extend(app_errors)
        else:
            errors.append("Missing apps directory")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def validate_app_structure(self, app_name: str) -> List[str]:
        """
        验证 Django app 结构
        
        Args:
            app_name: app 名称
            
        Returns:
            错误列表
        """
        errors = []
        app_path = self.root_path / "apps" / app_name
        
        if not app_path.exists():
            errors.append(f"App directory does not exist: {app_path}")
            return errors
        
        # 特殊 app 不需要验证标准结构
        # core: 核心工具模块，不是标准 Django app
        # tests: 测试目录，不是 Django app
        special_apps = {"core", "tests"}
        if app_name in special_apps:
            return errors
        
        # 检查必需的目录
        required_dirs = ["admin", "api", "services"]
        for dir_name in required_dirs:
            dir_path = app_path / dir_name
            if not dir_path.exists():
                errors.append(f"Missing directory in {app_name}: {dir_name}/")
            elif not dir_path.is_dir():
                errors.append(f"Expected directory but found file in {app_name}: {dir_name}")
        
        # 检查必需的文件
        required_files = ["__init__.py", "models.py", "schemas.py"]
        for file_name in required_files:
            file_path = app_path / file_name
            if not file_path.exists():
                errors.append(f"Missing file in {app_name}: {file_name}")
            elif not file_path.is_file():
                errors.append(f"Expected file but found directory in {app_name}: {file_name}")
        
        # 检查 migrations 目录
        migrations_path = app_path / "migrations"
        if not migrations_path.exists():
            errors.append(f"Missing migrations directory in {app_name}")
        
        return errors
    
    def validate_root_directory(self) -> List[str]:
        """
        验证根目录只包含必要文件
        
        Returns:
            错误列表
        """
        errors = []
        
        # 白名单：允许的文件和目录
        allowed_items = {
            # 核心目录
            "apiSystem", "apps", "tests", "scripts", "docs", "logs",
            # 缓存和生成目录
            ".hypothesis", ".mypy_cache", ".pytest_cache", "htmlcov", "__pycache__",
            # 配置文件
            ".env.example", ".env", ".gitignore", ".flake8", ".pre-commit-config.yaml",
            "conftest.py", "pytest.ini", "mypy.ini", "pyproject.toml",
            "requirements.txt", "Makefile", "README.md",
            # 系统文件
            ".DS_Store", ".git", "venv311", ".venv", "venv",
            # 临时文件（应该在 .gitignore 中）
            ".coverage", "IMPLEMENTATION_CHECKLIST.md",
            # IDE 配置
            ".idea", ".vscode", ".trae", ".kiro",
            # 遗留目录（待清理）
            "backend",
            # 遗留文档文件（待迁移到 docs/）
            "CODE_QUALITY_REVIEW.md",
            "DATA_RECOVERY_GUIDE.md",
            "PERFORMANCE_MONITORING_IMPLEMENTATION.md",
            "QUICK_START.md"
        }
        
        # 检查根目录
        for item in self.root_path.iterdir():
            if item.name not in allowed_items:
                errors.append(f"Unexpected item in root directory: {item.name}")
        
        # 检查必需的目录
        required_dirs = ["apiSystem", "apps", "scripts"]
        for dir_name in required_dirs:
            dir_path = self.root_path / dir_name
            if not dir_path.exists():
                errors.append(f"Missing required directory in root: {dir_name}/")
        
        return errors
    
    def validate_test_structure(self) -> List[str]:
        """
        验证测试目录结构
        
        Returns:
            错误列表
        """
        errors = []
        test_path = self.root_path / "tests"
        
        if not test_path.exists():
            # 测试目录不存在是警告，不是错误（因为可能还没迁移）
            return []
        
        # 检查必需的子目录
        required_dirs = ["unit", "integration", "property", "admin", "factories", "mocks"]
        for dir_name in required_dirs:
            dir_path = test_path / dir_name
            if not dir_path.exists():
                errors.append(f"Missing test subdirectory: tests/{dir_name}/")
        
        # 检查 conftest.py
        conftest_path = test_path / "conftest.py"
        if not conftest_path.exists():
            errors.append("Missing tests/conftest.py")
        
        return errors
    
    def validate_docs_structure(self) -> List[str]:
        """
        验证文档目录结构
        
        Returns:
            错误列表
        """
        errors = []
        docs_path = self.root_path / "docs"
        
        if not docs_path.exists():
            # 文档目录不存在是警告，不是错误（因为可能还没迁移）
            return []
        
        # 检查必需的子目录
        required_dirs = ["api", "architecture", "guides", "operations", "quality"]
        for dir_name in required_dirs:
            dir_path = docs_path / dir_name
            if not dir_path.exists():
                errors.append(f"Missing docs subdirectory: docs/{dir_name}/")
        
        # 检查 README.md
        readme_path = docs_path / "README.md"
        if not readme_path.exists():
            errors.append("Missing docs/README.md")
        
        return errors
    
    def get_app_list(self) -> List[str]:
        """
        获取所有 Django app 列表
        
        Returns:
            app 名称列表
        """
        apps_path = self.root_path / "apps"
        if not apps_path.exists():
            return []
        
        apps = []
        for item in apps_path.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name != '__pycache__':
                apps.append(item.name)
        
        return sorted(apps)
    
    def validate_scripts_structure(self) -> List[str]:
        """
        验证脚本目录结构
        
        Returns:
            错误列表
        """
        errors = []
        scripts_path = self.root_path / "scripts"
        
        if not scripts_path.exists():
            errors.append("Missing scripts directory")
            return errors
        
        # 检查推荐的子目录（不是必需的）
        recommended_dirs = ["testing", "development", "automation", "refactoring"]
        existing_subdirs = [
            d.name for d in scripts_path.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        ]
        
        # 这里不报错，只是检查
        return errors


def main():
    """主函数：运行验证"""
    import sys
    
    # 获取项目根目录
    if len(sys.argv) > 1:
        root_path = Path(sys.argv[1])
    else:
        # 默认使用当前目录的父目录（假设脚本在 scripts/refactoring/ 中）
        root_path = Path(__file__).parent.parent.parent
    
    print(f"验证项目结构: {root_path.absolute()}\n")
    
    # 创建验证器
    validator = ProjectStructureValidator(root_path)
    
    # 执行验证
    result = validator.validate_all()
    
    # 输出结果
    print(result)
    
    # 输出 app 列表
    apps = validator.get_app_list()
    if apps:
        print(f"\n发现 {len(apps)} 个 Django apps:")
        for app in apps:
            print(f"  - {app}")
    
    # 返回退出码
    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    main()
