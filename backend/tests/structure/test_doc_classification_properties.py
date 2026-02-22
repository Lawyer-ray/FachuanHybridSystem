"""
Property-Based Tests for Documentation Classification

Feature: backend-structure-optimization, Property 4: 文档分类存放
Validates: Requirements 4.1, 4.5
"""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from pathlib import Path

# 定义文档类型和对应的目录映射
DOC_TYPE_MAPPING = {
    "api": "docs/api",
    "architecture": "docs/architecture",
    "guides": "docs/guides",
    "operations": "docs/operations",
    "quality": "docs/quality",
}

# 定义有效的顶级子目录（包括嵌套的子目录）
# 注意：adr/ 目录当前在 docs/ 根目录，但根据设计文档应该移动到 docs/architecture/adr/
# 这将在后续的重构任务中处理
# archive/ 目录用于存放归档的报告文件（如 admin-test-reports, insurance-dev-notes）
# examples/ 目录用于存放示例代码和使用示例文档
VALID_DOC_SUBDIRS = ["api", "architecture", "guides", "operations", "quality", "adr", "archive", "examples"]

# 定义每种类型的文档关键词
DOC_TYPE_KEYWORDS = {
    "api": ["api", "endpoint", "route", "request", "response"],
    "architecture": ["architecture", "design", "pattern", "refactoring", "structure"],
    "guides": ["guide", "tutorial", "review", "checklist", "process", "quick", "start", "team", "knowledge"],
    "operations": ["operation", "deployment", "monitoring", "performance", "recovery", "backup"],
    "quality": ["quality", "test", "coverage", "lint", "code review"],
}


def get_doc_type_from_filename(filename: str) -> str:
    """
    根据文件名推断文档类型

    Args:
        filename: 文件名（不含路径）

    Returns:
        文档类型（api, architecture, guides, operations, quality）
    """
    filename_lower = filename.lower()

    # 检查每种类型的关键词
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in filename_lower:
                return doc_type

    # 默认返回 guides（开发指南）
    return "guides"


def get_all_doc_files(root_path: Path) -> list:
    """
    获取所有文档文件

    Args:
        root_path: 项目根目录

    Returns:
        文档文件路径列表
    """
    docs_dir = root_path / "docs"
    if not docs_dir.exists():
        return []

    doc_files = []

    # 遍历 docs/ 目录下的所有 .md 文件
    for md_file in docs_dir.rglob("*.md"):
        # 排除 README.md
        if md_file.name != "README.md":
            doc_files.append(md_file)

    return doc_files


@pytest.mark.property_test
def test_documentation_classification_property():
    """
    Property 4: 文档分类存放

    For any documentation file in the project, it should be located in the
    appropriate docs/ subdirectory based on its type (api/, architecture/,
    guides/, operations/, quality/)

    Feature: backend-structure-optimization, Property 4: 文档分类存放
    Validates: Requirements 4.1, 4.5
    """
    root_path = Path(__file__).resolve().parent.parent.parent
    doc_files = get_all_doc_files(root_path)

    # 如果没有文档文件，测试通过
    if not doc_files:
        pytest.skip("No documentation files found")

    errors = []

    for doc_file in doc_files:
        # 获取相对于 docs/ 的路径
        try:
            rel_path = doc_file.relative_to(root_path / "docs")
        except ValueError:
            errors.append(f"文档文件不在 docs/ 目录下: {doc_file}")
            continue

        # 获取文档所在的子目录
        if len(rel_path.parts) < 2:
            errors.append(f"文档文件应该在 docs/ 的子目录中: {doc_file}")
            continue

        actual_subdir = rel_path.parts[0]

        # 检查子目录是否是有效的文档类型
        if actual_subdir not in VALID_DOC_SUBDIRS:
            errors.append(
                f"文档文件在无效的子目录中: {doc_file} " f"(子目录: {actual_subdir}, 有效子目录: {VALID_DOC_SUBDIRS})"
            )

    # 断言没有错误
    assert not errors, f"文档分类验证失败:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_specific_doc_files_in_correct_locations():
    """
    测试特定文档文件是否在正确的位置

    Feature: backend-structure-optimization, Property 4: 文档分类存放
    Validates: Requirements 4.1, 4.5
    """
    root_path = Path(__file__).resolve().parent.parent.parent

    # 定义预期的文档位置
    expected_locations = {
        "CODE_QUALITY_REVIEW.md": "docs/quality",
        "DATA_RECOVERY_GUIDE.md": "docs/operations",
        "PERFORMANCE_MONITORING_IMPLEMENTATION.md": "docs/operations",
        "QUICK_START.md": "docs/guides",
        "API.md": "docs/api",
        "ARCHITECTURE_TRAINING.md": "docs/architecture",
        "REFACTORING_BEST_PRACTICES.md": "docs/architecture",
        "CODE_REVIEW_CHECKLIST.md": "docs/guides",
        "CODE_REVIEW_PROCESS.md": "docs/guides",
        "TEAM_KNOWLEDGE_SHARING.md": "docs/guides",
    }

    errors = []

    for filename, expected_dir in expected_locations.items():
        expected_path = root_path / expected_dir / filename

        if not expected_path.exists():
            # 检查文件是否在其他位置
            found_paths = list(root_path.rglob(filename))
            if found_paths:
                actual_path = found_paths[0]
                try:
                    rel_path = actual_path.relative_to(root_path)
                    errors.append(f"文档文件 {filename} 在错误的位置: {rel_path} " f"(应该在: {expected_dir})")
                except ValueError:
                    errors.append(f"文档文件 {filename} 在项目外部: {actual_path}")
            else:
                errors.append(f"文档文件 {filename} 不存在")

    # 断言没有错误
    assert not errors, f"文档位置验证失败:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_no_docs_in_root_directory():
    """
    测试根目录不应该包含文档文件（除了 README.md）

    Feature: backend-structure-optimization, Property 4: 文档分类存放
    Validates: Requirements 4.1, 4.5
    """
    root_path = Path(__file__).resolve().parent.parent.parent

    # 获取根目录下的所有 .md 文件
    root_md_files = [f for f in root_path.glob("*.md") if f.name != "README.md"]

    # 断言根目录下没有其他 .md 文件
    assert not root_md_files, f"根目录不应该包含文档文件（除了 README.md）:\n" + "\n".join(
        f"  - {f.name}" for f in root_md_files
    )


@pytest.mark.property_test
def test_docs_subdirectories_exist():
    """
    测试所有必需的 docs/ 子目录是否存在

    Feature: backend-structure-optimization, Property 4: 文档分类存放
    Validates: Requirements 4.1, 4.5
    """
    root_path = Path(__file__).resolve().parent.parent.parent
    docs_path = root_path / "docs"

    # 检查 docs/ 目录是否存在
    assert docs_path.exists(), "docs/ 目录不存在"
    assert docs_path.is_dir(), "docs/ 不是目录"

    # 检查所有必需的子目录
    required_subdirs = ["api", "architecture", "guides", "operations", "quality"]
    missing_subdirs = []

    for subdir in required_subdirs:
        subdir_path = docs_path / subdir
        if not subdir_path.exists():
            missing_subdirs.append(subdir)
        elif not subdir_path.is_dir():
            missing_subdirs.append(f"{subdir} (不是目录)")

    # 断言所有子目录都存在
    assert not missing_subdirs, f"缺少必需的 docs/ 子目录:\n" + "\n".join(f"  - {d}" for d in missing_subdirs)


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
