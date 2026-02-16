#!/usr/bin/env python3
"""批量修复变量类型注解缺失的错误

修复内容：
1. 识别缺少类型注解的变量
2. 添加明确的类型注解
3. 处理Optional和Union类型
4. 基于赋值推断类型

Requirements: 2.1, 2.4
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class VariableAnnotationAnalyzer(ast.NodeVisitor):
    """分析变量类型注解的 AST 访问器"""

    def __init__(self) -> None:
        self.variables_to_fix: list[dict[str, Any]] = []
        self.current_function: str | None = None
        self.current_class: str | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """访问类定义"""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """访问函数定义"""
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """访问异步函数定义"""
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_Assign(self, node: ast.Assign) -> None:
        """访问赋值语句"""
        # 只处理简单的变量赋值（不处理元组解包等复杂情况）
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0]
            var_name = target.id

            # 跳过特殊变量（单下划线开头的私有变量）
            if var_name.startswith("_") and not (var_name.startswith("__") and var_name.endswith("__")):
                self.generic_visit(node)
                return

            # 跳过 dunder 变量（除了 __all__）
            if var_name.startswith("__") and var_name.endswith("__") and var_name != "__all__":
                self.generic_visit(node)
                return

            # 跳过常量（全大写）
            if var_name.isupper():
                self.generic_visit(node)
                return

            # 只处理模块级和类级变量（不处理函数内局部变量）
            if self.current_function is None:
                inferred_type = self._infer_type(node.value)
                if inferred_type:
                    self.variables_to_fix.append(
                        {
                            "name": var_name,
                            "lineno": node.lineno,
                            "col_offset": node.col_offset,
                            "type": inferred_type,
                            "in_class": self.current_class,
                        }
                    )

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """访问带注解的赋值语句（已有注解，跳过）"""
        self.generic_visit(node)

    def _infer_type(self, node: ast.expr) -> str | None:
        """推断表达式类型"""
        if isinstance(node, ast.Constant):
            value = node.value
            if value is None:
                return "Any | None"
            elif isinstance(value, bool):
                return "bool"
            elif isinstance(value, int):
                return "int"
            elif isinstance(value, float):
                return "float"
            elif isinstance(value, str):
                return "str"
            elif isinstance(value, bytes):
                return "bytes"
        elif isinstance(node, ast.List):
            # 尝试推断列表元素类型
            if node.elts:
                elem_types = set()
                for elt in node.elts[:5]:  # 只检查前5个元素
                    elem_type = self._infer_type(elt)
                    if elem_type:
                        elem_types.add(elem_type)

                if len(elem_types) == 1:
                    return f"list[{elem_types.pop()}]"
            return "list[Any]"
        elif isinstance(node, ast.Dict):
            # 尝试推断字典键值类型
            if node.keys and node.values:
                key_types = set()
                val_types = set()
                for key, val in zip(node.keys[:5], node.values[:5]):  # 只检查前5对
                    if key:
                        key_type = self._infer_type(key)
                        if key_type:
                            key_types.add(key_type)
                    val_type = self._infer_type(val)
                    if val_type:
                        val_types.add(val_type)

                if len(key_types) == 1 and len(val_types) == 1:
                    return f"dict[{key_types.pop()}, {val_types.pop()}]"
            return "dict[str, Any]"
        elif isinstance(node, ast.Set):
            # 尝试推断集合元素类型
            if node.elts:
                elem_types = set()
                for elt in node.elts[:5]:
                    elem_type = self._infer_type(elt)
                    if elem_type:
                        elem_types.add(elem_type)

                if len(elem_types) == 1:
                    return f"set[{elem_types.pop()}]"
            return "set[Any]"
        elif isinstance(node, ast.Tuple):
            # 元组类型较复杂，使用通用类型
            return "tuple[Any, ...]"
        elif isinstance(node, ast.Call):
            # 从函数调用推断类型
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in ("dict", "Dict"):
                    return "dict[str, Any]"
                elif func_name in ("list", "List"):
                    return "list[Any]"
                elif func_name in ("set", "Set"):
                    return "set[Any]"
                elif func_name in ("tuple", "Tuple"):
                    return "tuple[Any, ...]"
                elif func_name in ("str",):
                    return "str"
                elif func_name in ("int",):
                    return "int"
                elif func_name in ("float",):
                    return "float"
                elif func_name in ("bool",):
                    return "bool"
        elif isinstance(node, ast.BinOp):
            # 二元操作，尝试推断
            left_type = self._infer_type(node.left)
            right_type = self._infer_type(node.right)
            if left_type == right_type:
                return left_type
        elif isinstance(node, ast.IfExp):
            # 三元表达式，推断两个分支的类型
            true_type = self._infer_type(node.body)
            false_type = self._infer_type(node.orelse)
            if true_type == false_type:
                return true_type
            elif true_type and false_type:
                return f"{true_type} | {false_type}"

        return None


def fix_type_annotations(content: str, file_path: Path) -> tuple[str, dict[str, int]]:
    """为变量添加类型注解

    Returns:
        (修复后的内容, 修复统计)
    """
    stats = {
        "module_vars": 0,
        "class_vars": 0,
    }

    try:
        tree = ast.parse(content)
    except SyntaxError:
        logger.warning(f"语法错误，跳过: {file_path}")
        return content, stats

    analyzer = VariableAnnotationAnalyzer()
    analyzer.visit(tree)

    if not analyzer.variables_to_fix:
        return content, stats

    # 按行号倒序排序，从后往前修改，避免行号偏移
    variables = sorted(analyzer.variables_to_fix, key=lambda x: x["lineno"], reverse=True)

    lines = content.split("\n")

    for var in variables:
        lineno = var["lineno"] - 1  # AST 行号从 1 开始
        var_name = var["name"]
        var_type = var["type"]

        if lineno >= len(lines):
            continue

        line = lines[lineno]

        # 查找变量名和等号的位置
        # 格式: var_name = value
        # 转换为: var_name: type = value

        # 使用正则表达式匹配变量赋值
        import re

        pattern = rf"\b{re.escape(var_name)}\s*="
        match = re.search(pattern, line)

        if match:
            # 找到变量名后的等号位置
            eq_pos = match.end() - 1  # 等号的位置

            # 在等号前插入类型注解
            new_line = line[:eq_pos] + f": {var_type} " + line[eq_pos:]
            lines[lineno] = new_line

            if var["in_class"]:
                stats["class_vars"] += 1
            else:
                stats["module_vars"] += 1

    modified_content = "\n".join(lines)

    # 检查是否需要添加 Any 导入
    if "Any" in modified_content and (stats["module_vars"] > 0 or stats["class_vars"] > 0):
        modified_content = ensure_typing_imports(modified_content)

    return modified_content, stats


def ensure_typing_imports(content: str) -> str:
    """确保导入了必要的类型"""
    # 检查是否已经导入了 Any
    if re.search(r"from typing import.*\bAny\b", content):
        return content

    lines = content.split("\n")

    # 查找 from typing import 行
    typing_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_import_idx = i
            break

    if typing_import_idx >= 0:
        # 在现有导入中添加 Any
        line = lines[typing_import_idx]

        # 处理多行导入（括号）
        if "(" in line:
            # 查找右括号
            for j in range(typing_import_idx, len(lines)):
                if ")" in lines[j]:
                    # 检查是否已有 Any
                    import_block = "\n".join(lines[typing_import_idx : j + 1])
                    if "Any" not in import_block:
                        lines[j] = lines[j].replace(")", ", Any)")
                    break
        else:
            # 单行导入，检查是否已有 Any
            if "Any" not in line:
                lines[typing_import_idx] = line.rstrip() + ", Any"
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

        lines.insert(insert_idx, "from typing import Any")
        if insert_idx + 1 < len(lines) and lines[insert_idx + 1].strip():
            lines.insert(insert_idx + 1, "")

    return "\n".join(lines)


def fix_file(file_path: Path) -> dict[str, Any]:
    """修复单个文件

    Returns:
        修复结果字典
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # 修复类型注解
        content, stats = fix_type_annotations(content, file_path)

        # 只有在有修改时才写入
        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return {"success": True, "modified": True, "stats": stats}

        return {"success": True, "modified": False, "stats": stats}

    except Exception as e:
        logger.error(f"错误处理文件 {file_path}: {e}")
        return {"success": False, "modified": False, "error": str(e)}


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    apps_path = backend_path / "apps"

    if not apps_path.exists():
        logger.error(f"apps 目录不存在: {apps_path}")
        return

    logger.info("开始批量修复变量类型注解缺失错误...")
    logger.info(f"扫描目录: {apps_path}\n")

    total_stats = {
        "files": 0,
        "module_vars": 0,
        "class_vars": 0,
    }

    # 遍历所有 Python 文件
    py_files = list(apps_path.rglob("*.py"))
    logger.info(f"找到 {len(py_files)} 个 Python 文件\n")

    for py_file in py_files:
        # 跳过 __init__.py 和 migrations
        if py_file.name == "__init__.py" or "migrations" in py_file.parts:
            continue

        result = fix_file(py_file)
        if result["success"] and result["modified"]:
            stats = result["stats"]
            total_stats["files"] += 1
            total_stats["module_vars"] += stats["module_vars"]
            total_stats["class_vars"] += stats["class_vars"]

            rel_path = py_file.relative_to(backend_path)
            logger.info(f"✓ {rel_path}")
            if any(stats.values()):
                fixes = []
                if stats["module_vars"] > 0:
                    fixes.append(f"模块变量: {stats['module_vars']}")
                if stats["class_vars"] > 0:
                    fixes.append(f"类变量: {stats['class_vars']}")
                logger.info(f"  {', '.join(fixes)}")

    logger.info(f"\n修复完成:")
    logger.info(f"  修复文件数: {total_stats['files']}")
    logger.info(f"  模块变量注解: {total_stats['module_vars']}")
    logger.info(f"  类变量注解: {total_stats['class_vars']}")
    total_fixes = total_stats["module_vars"] + total_stats["class_vars"]
    logger.info(f"  总修复数: {total_fixes}")


if __name__ == "__main__":
    main()
