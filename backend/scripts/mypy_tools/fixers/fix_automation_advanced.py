#!/usr/bin/env python3
"""高级修复 automation 模块剩余类型错误

修复内容：
1. **kwargs 缺少类型注解
2. extra 字典缺少类型注解
3. 其他复杂类型错误

Requirements: 4.8
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def fix_kwargs_type(content: str) -> tuple[str, int]:
    """修复 **kwargs 缺少类型注解"""
    fixes = 0

    # 修复 **kwargs) ->
    pattern = r"(\*\*kwargs)(\s*\)\s*->)"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"**kwargs: Any\2", content)
        fixes += len(matches)

    # 修复 **kwargs,
    pattern = r"(\*\*kwargs)(\s*,)"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"**kwargs: Any\2", content)
        fixes += len(matches)

    return content, fixes


def fix_extra_dict_type(content: str) -> tuple[str, int]:
    """修复 extra 字典缺少类型注解"""
    fixes = 0

    # 修复 extra={
    pattern = r"\n(\s+)extra\s*=\s*\{"
    matches = list(re.finditer(pattern, content))
    if matches:
        content = re.sub(pattern, r"\n\1extra: Dict[str, Any] = {", content)
        fixes += len(matches)

    return content, fixes


def ensure_dict_any_import(content: str) -> str:
    """确保导入了 Dict 和 Any"""
    # 检查是否需要 Dict
    needs_dict = "Dict[str, Any]" in content
    needs_any = "Any" in content or "**kwargs: Any" in content

    if not needs_dict and not needs_any:
        return content

    # 检查现有导入
    has_dict = bool(re.search(r"from typing import.*\bDict\b", content))
    has_any = bool(re.search(r"from typing import.*\bAny\b", content))

    imports_needed = []
    if needs_dict and not has_dict:
        imports_needed.append("Dict")
    if needs_any and not has_any:
        imports_needed.append("Any")

    if not imports_needed:
        return content

    lines = content.split("\n")

    # 查找 from typing import 行
    typing_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_import_idx = i
            break

    if typing_import_idx >= 0:
        # 在现有导入中添加
        line = lines[typing_import_idx]

        # 处理多行导入
        if "(" in line:
            # 在括号内添加
            for j in range(typing_import_idx, len(lines)):
                if ")" in lines[j]:
                    lines[j] = lines[j].replace(")", f', {", ".join(imports_needed)})')
                    break
        else:
            # 单行导入
            lines[typing_import_idx] = line.rstrip() + f', {", ".join(imports_needed)}'
    else:
        # 添加新的导入行
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from __future__"):
                insert_idx = i + 1
                while insert_idx < len(lines) and not lines[insert_idx].strip():
                    insert_idx += 1
                break
            elif line.startswith("import ") or line.startswith("from "):
                insert_idx = i
                break

        lines.insert(insert_idx, f'from typing import {", ".join(imports_needed)}')
        if insert_idx + 1 < len(lines) and lines[insert_idx + 1].strip():
            lines.insert(insert_idx + 1, "")

    return "\n".join(lines)


def fix_file(file_path: Path) -> dict[str, Any]:
    """修复单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        stats = {
            "kwargs": 0,
            "extra_dict": 0,
        }

        # 修复 **kwargs 类型
        content, kwargs_fixes = fix_kwargs_type(content)
        stats["kwargs"] = kwargs_fixes

        # 修复 extra 字典类型
        content, extra_fixes = fix_extra_dict_type(content)
        stats["extra_dict"] = extra_fixes

        # 确保导入必要的类型
        if stats["kwargs"] > 0 or stats["extra_dict"] > 0:
            content = ensure_dict_any_import(content)

        # 只有在有修改时才写入
        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return {"success": True, "stats": stats}

        return {"success": True, "stats": {"kwargs": 0, "extra_dict": 0}}

    except Exception as e:
        logger.error(f"错误处理文件 {file_path}: {e}")
        return {"success": False, "error": str(e)}


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / "apps" / "automation"

    if not automation_path.exists():
        logger.error(f"automation 目录不存在: {automation_path}")
        return

    logger.info("开始高级修复 automation 模块类型错误...")
    logger.info(f"扫描目录: {automation_path}")

    total_stats = {
        "files": 0,
        "kwargs": 0,
        "extra_dict": 0,
    }

    # 遍历所有 Python 文件（排除已修复的模块）
    py_files = []
    for py_file in automation_path.rglob("*.py"):
        # 排除 document_delivery, sms, scraper
        rel_path = py_file.relative_to(automation_path)
        if any(part in str(rel_path) for part in ["document_delivery", "/sms/", "/scraper/"]):
            continue
        if py_file.name != "__init__.py":
            py_files.append(py_file)

    logger.info(f"找到 {len(py_files)} 个需要检查的 Python 文件\n")

    for py_file in py_files:
        result = fix_file(py_file)
        if result["success"] and any(result["stats"].values()):
            stats = result["stats"]
            total_stats["files"] += 1
            total_stats["kwargs"] += stats["kwargs"]
            total_stats["extra_dict"] += stats["extra_dict"]

            rel_path = py_file.relative_to(backend_path)
            logger.info(f"✓ {rel_path}")
            logger.info(f"  kwargs: {stats['kwargs']}, extra_dict: {stats['extra_dict']}")

    logger.info(f"\n修复完成:")
    logger.info(f"  修复文件数: {total_stats['files']}")
    logger.info(f"  kwargs 修复: {total_stats['kwargs']}")
    logger.info(f"  extra_dict 修复: {total_stats['extra_dict']}")
    logger.info(f"  总修复数: {total_stats['kwargs'] + total_stats['extra_dict']}")


if __name__ == "__main__":
    main()
