"""Django app 结构验证器"""

from __future__ import annotations

from pathlib import Path


class ProjectStructureValidator:
    """验证 Django 项目的 app 目录结构"""

    REQUIRED_DIRS = ("admin", "api", "services", "migrations")
    REQUIRED_FILES = ("__init__.py",)

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.apps_path = project_root / "apps"

    def get_app_list(self) -> list[str]:
        """返回所有 Django app 名称"""
        if not self.apps_path.exists():
            return []
        return [
            item.name
            for item in self.apps_path.iterdir()
            if item.is_dir() and not item.name.startswith(".") and item.name != "__pycache__"
        ]

    def validate_app_structure(self, app_name: str) -> list[str]:
        """验证单个 app 的目录结构，返回错误列表（空列表表示通过）"""
        app_path = self.apps_path / app_name
        if not app_path.exists():
            return [f"App directory does not exist: {app_path}"]

        errors: list[str] = []
        for required_dir in self.REQUIRED_DIRS:
            dir_path = app_path / required_dir
            if not dir_path.exists():
                errors.append(f"Missing required directory: {app_name}/{required_dir}/")

        for required_file in self.REQUIRED_FILES:
            file_path = app_path / required_file
            if not file_path.exists():
                errors.append(f"Missing required file: {app_name}/{required_file}")

        return errors

    # 根目录允许的文件
    ALLOWED_ROOT_FILES: frozenset[str] = frozenset(
        {
            "README.md",
            "AGENTS.md",
            "Makefile",
            "Dockerfile",
            "docker-compose.yml",
            "docker-entrypoint.sh",
            "pytest.ini",
            "mypy.ini",
            "pyproject.toml",
            "ruff.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "requirements-test.txt",
            "conftest.py",
            ".dockerignore",
            ".env.example",
            ".env",
            ".env.dev",
            ".gitignore",
            ".pre-commit-config.yaml",
            ".secrets.baseline",
            ".secrets.baseline.new",
            ".coverage",
            ".DS_Store",
            "IMPLEMENTATION_CHECKLIST.md",
            # uv 包管理器的锁文件，项目使用 uv 替代 pip
            "uv.lock",
        }
    )

    # 根目录允许的目录
    ALLOWED_ROOT_DIRS: frozenset[str] = frozenset(
        {
            "apiSystem",
            "apps",
            "tests",
            "scripts",
            "docs",
            "deploy",
            "logs",
            "htmlcov",
            ".hypothesis",
            ".mypy_cache",
            ".pytest_cache",
            ".git",
            ".idea",
            ".vscode",
            ".trae",
            ".kiro",
            ".ruff_cache",
            "venv311",
            "venv312",
            ".venv",
            "venv",
            "__pycache__",
            ".cache",
            "media",
            "constraints",
            "devtools",
            "tests_smoke",
            "mcp_server",
            "cookies",
        }
    )

    # 根目录必需的目录
    REQUIRED_ROOT_DIRS: tuple[str, ...] = ("apiSystem", "apps", "scripts")

    def validate_root_directory(self) -> list[str]:
        """验证根目录结构，返回错误列表（空列表表示通过）"""
        errors: list[str] = []

        # 检查必需目录是否存在
        for required_dir in self.REQUIRED_ROOT_DIRS:
            dir_path = self.project_root / required_dir
            if not dir_path.exists():
                errors.append(f"Missing required directory: {required_dir}/")

        # 检查根目录中是否有意外的项目
        for item in self.project_root.iterdir():
            name = item.name
            if item.is_dir():
                if name not in self.ALLOWED_ROOT_DIRS:
                    errors.append(f"Unexpected item in root directory: {name}")
            else:
                if name not in self.ALLOWED_ROOT_FILES:
                    errors.append(f"Unexpected item in root directory: {name}")

        return errors
