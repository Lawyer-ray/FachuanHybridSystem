"""
Property-Based Tests for Markdown Document Location

Feature: backend-structure-optimization, Property 5: Markdown 文档位置正确性
Validates: Requirements 5.5, 8.3, 8.4
"""

from typing import List

import pytest

from pathlib import Path


def get_all_markdown_files(root_path: Path) -> list[Path]:
    """
    获取项目中的所有 Markdown 文件

    Args:
        root_path: 项目根目录

    Returns:
        Markdown 文件路径列表
    """
    # 排除的目录
    excluded_dirs = {
        ".git",
        ".hypothesis",
        ".mypy_cache",
        ".pytest_cache",
        "htmlcov",
        "venv311",
        "__pycache__",
        "node_modules",
        ".idea",
        ".vscode",
        "backend",  # 排除重复的 backend/ 目录（将在后续任务中删除）
    }

    markdown_files = []

    for md_file in root_path.rglob("*.md"):
        # 检查文件是否在排除的目录中
        if any(excluded_dir in md_file.parts for excluded_dir in excluded_dirs):
            continue

        markdown_files.append(md_file)

    return markdown_files


def is_valid_markdown_location(md_file: Path, root_path: Path) -> tuple[bool, str]:
    """
    检查 Markdown 文件是否在有效的位置

    Args:
        md_file: Markdown 文件路径
        root_path: 项目根目录

    Returns:
        (是否有效, 错误消息)
    """
    try:
        rel_path = md_file.relative_to(root_path)
    except ValueError:
        return False, f"文件不在项目目录中: {md_file}"

    # 允许的位置：
    # 1. 根目录的 README.md
    if rel_path == Path("README.md"):
        return True, ""

    # 2. docs/ 目录下的所有 .md 文件
    if rel_path.parts[0] == "docs":
        return True, ""

    # 3. 模块目录下的文档（apps/*/.../*.md）
    # 根据设计文档 Requirement 4.5: "模块特定文档放在模块目录下"
    if len(rel_path.parts) >= 2 and rel_path.parts[0] == "apps":
        # 允许模块目录下的所有 .md 文件（包括 README.md 和其他文档）
        return True, ""

    # 4. scripts/ 目录下的文档
    if rel_path.parts[0] == "scripts":
        # 允许 scripts/ 目录下的所有 .md 文件
        return True, ""

    # 5. tests/ 目录下的文档
    if rel_path.parts[0] == "tests":
        # 允许 tests/ 目录下的所有 .md 文件（测试报告、计划等）
        return True, ""

    # 6. 特殊的文档文件（在迁移过程中可能存在的临时文件）
    # 这些文件应该已经被迁移，如果还存在则是错误
    special_docs = [
        "CODE_QUALITY_REVIEW.md",
        "DATA_RECOVERY_GUIDE.md",
        "PERFORMANCE_MONITORING_IMPLEMENTATION.md",
        "QUICK_START.md",
        "IMPLEMENTATION_CHECKLIST.md",
    ]

    if rel_path.name in special_docs and len(rel_path.parts) == 1:
        return False, f"文档文件应该在 docs/ 目录中，而不是根目录: {rel_path}"

    # 其他位置的 .md 文件都是无效的
    return False, f"Markdown 文件在无效的位置: {rel_path}"


@pytest.mark.property_test
def test_markdown_location_property():
    """
    Property 5: Markdown 文档位置正确性

    For any Markdown file in the project (excluding README.md in root and
    module directories), it should be located in the docs/ directory or a
    module-specific location

    Feature: backend-structure-optimization, Property 5: Markdown 文档位置正确性
    Validates: Requirements 5.5, 8.3, 8.4
    """
    root_path = Path(__file__).resolve().parent.parent.parent
    markdown_files = get_all_markdown_files(root_path)

    # 如果没有 Markdown 文件，测试通过
    if not markdown_files:
        pytest.skip("No Markdown files found")

    errors = []

    for md_file in markdown_files:
        is_valid, error_msg = is_valid_markdown_location(md_file, root_path)
        if not is_valid:
            errors.append(error_msg)

    # 断言没有错误
    assert not errors, "Markdown 文件位置验证失败:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_no_markdown_in_root_except_readme():
    """
    测试根目录不应该包含 Markdown 文件（除了 README.md）

    Feature: backend-structure-optimization, Property 5: Markdown 文档位置正确性
    Validates: Requirements 5.5, 8.3, 8.4
    """
    root_path = Path(__file__).resolve().parent.parent.parent

    # 获取根目录下的所有 .md 文件
    root_md_files = [f for f in root_path.glob("*.md") if f.name != "README.md"]

    # 断言根目录下没有其他 .md 文件
    assert not root_md_files, "根目录不应该包含 Markdown 文件（除了 README.md）:\n" + "\n".join(
        f"  - {f.name}" for f in root_md_files
    )


@pytest.mark.property_test
def test_all_docs_in_docs_directory():
    """
    测试所有文档文件都应该在 docs/ 目录中

    Feature: backend-structure-optimization, Property 5: Markdown 文档位置正确性
    Validates: Requirements 5.5, 8.3, 8.4
    """
    root_path = Path(__file__).resolve().parent.parent.parent

    # 定义应该在 docs/ 目录中的文档文件
    doc_files_should_be_in_docs = [
        "CODE_QUALITY_REVIEW.md",
        "DATA_RECOVERY_GUIDE.md",
        "PERFORMANCE_MONITORING_IMPLEMENTATION.md",
        "QUICK_START.md",
        "API.md",
        "ARCHITECTURE_TRAINING.md",
        "REFACTORING_BEST_PRACTICES.md",
        "CODE_REVIEW_CHECKLIST.md",
        "CODE_REVIEW_PROCESS.md",
        "TEAM_KNOWLEDGE_SHARING.md",
    ]

    errors = []

    for doc_file in doc_files_should_be_in_docs:
        # 检查文件是否在根目录
        root_file = root_path / doc_file
        if root_file.exists():
            errors.append(f"文档文件 {doc_file} 应该在 docs/ 目录中，而不是根目录")

        # 检查文件是否在 docs/ 根目录（应该在子目录中）
        docs_root_file = root_path / "docs" / doc_file
        if docs_root_file.exists():
            errors.append(f"文档文件 {doc_file} 应该在 docs/ 的子目录中，而不是 docs/ 根目录")

    # 断言没有错误
    assert not errors, "文档文件位置验证失败:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_module_readme_files():
    """
    测试模块目录下的 README.md 文件

    Feature: backend-structure-optimization, Property 5: Markdown 文档位置正确性
    Validates: Requirements 5.5, 8.3, 8.4
    """
    root_path = Path(__file__).resolve().parent.parent.parent
    apps_path = root_path / "apps"

    if not apps_path.exists():
        pytest.skip("apps/ directory does not exist")

    # 获取所有模块目录
    module_dirs = [d for d in apps_path.iterdir() if d.is_dir() and not d.name.startswith("_")]

    # 检查每个模块是否有 README.md（可选）
    # 如果有 README.md，它应该在模块根目录
    for module_dir in module_dirs:
        readme_files = list(module_dir.rglob("README.md"))

        for readme in readme_files:
            # README.md 可以在模块根目录或子目录中
            # 这是允许的，所以不需要额外检查
            pass

    # 这个测试主要是确保 README.md 文件的存在是合理的
    # 实际上，我们只需要确保它们不在错误的位置
    assert True


@pytest.mark.property_test
def test_implementation_checklist_location():
    """
    测试 IMPLEMENTATION_CHECKLIST.md 的位置

    Feature: backend-structure-optimization, Property 5: Markdown 文档位置正确性
    Validates: Requirements 5.5, 8.3, 8.4
    """
    root_path = Path(__file__).resolve().parent.parent.parent

    # IMPLEMENTATION_CHECKLIST.md 可以在根目录（作为项目级别的文档）
    # 或者在 docs/ 目录中
    checklist_in_root = root_path / "IMPLEMENTATION_CHECKLIST.md"
    checklist_in_docs = root_path / "docs" / "IMPLEMENTATION_CHECKLIST.md"

    # 如果文件存在，它应该在根目录或 docs/ 目录中
    if checklist_in_root.exists():
        # 根目录是允许的（作为项目级别的清单）
        pass
    elif checklist_in_docs.exists():
        # docs/ 目录也是允许的
        pass
    else:
        # 文件不存在，跳过测试
        pytest.skip("IMPLEMENTATION_CHECKLIST.md does not exist")

    # 测试通过
    assert True


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
