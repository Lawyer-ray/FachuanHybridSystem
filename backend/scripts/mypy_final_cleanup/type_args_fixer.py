"""TypeArgsFixer - 自动补充泛型类型参数"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from .backup_manager import BackupManager

logger = logging.getLogger(__name__)


class TypeArgsFixer:
    """自动补充泛型类型参数（List → List[Any], Dict → Dict[str, Any]）"""

    def __init__(self, backup_manager: BackupManager | None = None) -> None:
        """
        初始化TypeArgsFixer

        Args:
            backup_manager: 备份管理器，如果为None则创建新实例
        """
        self.backup_manager = backup_manager or BackupManager()

        # 需要添加的typing导入
        self.required_imports: set[str] = set()

    def fix_file(self, file_path: str) -> int:
        """
        修复文件中的type-arg错误

        Args:
            file_path: 文件路径（相对于backend目录）

        Returns:
            修复的错误数量
        """
        try:
            # 备份文件
            backup_path = self.backup_manager.backup_file(file_path)
            if backup_path is None:
                logger.error(f"无法备份文件: {file_path}")
                return 0

            # 读取文件内容
            full_path = self.backup_manager.backend_path / file_path
            content = full_path.read_text(encoding="utf-8")

            # 重置导入集合
            self.required_imports = set()

            # 应用修复
            original_content = content
            content = self.fix_list_types(content)
            content = self.fix_dict_types(content)
            content = self.fix_set_types(content)
            content = self.fix_tuple_types(content)

            # 添加缺失的导入
            if self.required_imports:
                content = self._add_missing_imports(content)

            # 如果有修改，写回文件
            if content != original_content:
                full_path.write_text(content, encoding="utf-8")
                fixes_count = self._count_fixes(original_content, content)
                logger.info(f"已修复 {file_path}: {fixes_count}处")
                return fixes_count

            return 0

        except Exception as e:
            logger.error(f"修复文件失败 {file_path}: {e}")
            # 尝试恢复备份
            self.backup_manager.restore_file(file_path)
            return 0

    def fix_list_types(self, content: str) -> str:
        """
        修复List/list类型参数

        将 List 或 list 转换为 List[Any]

        Args:
            content: 文件内容

        Returns:
            修复后的内容
        """
        # 匹配类型注解中的List或list（不带类型参数）
        # 匹配模式：
        # 1. -> List 或 -> list（返回类型）
        # 2. : List 或 : list（变量类型）
        # 3. List | 或 list |（Union类型）
        # 4. | List 或 | list（Union类型）
        # 5. (List) 或 (list)（括号中）

        patterns = [
            # 返回类型注解：-> List 或 -> list
            (r"(->)\s+(List|list)(\s*[:\n,\)])", r"\1 List[Any]\3"),
            # 变量类型注解：: List 或 : list
            (r"(:\s*)(List|list)(\s*[=\n,\)])", r"\1List[Any]\3"),
            # Union类型：List | 或 list |
            (r"(List|list)(\s*\|)", r"List[Any]\2"),
            # Union类型：| List 或 | list
            (r"(\|\s*)(List|list)(\s*[,\)\n])", r"\1List[Any]\3"),
            # 括号中：(List) 或 (list)
            (r"(\()(List|list)(\))", r"\1List[Any]\3"),
        ]

        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)

        # 标记需要导入
        if "List[Any]" in content:
            self.required_imports.add("List")
            self.required_imports.add("Any")

        return content

    def fix_dict_types(self, content: str) -> str:
        """
        修复Dict/dict类型参数

        将 Dict 或 dict 转换为 Dict[str, Any]

        Args:
            content: 文件内容

        Returns:
            修复后的内容
        """
        patterns = [
            # 返回类型注解：-> Dict 或 -> dict
            (r"(->)\s+(Dict|dict)(\s*[:\n,\)])", r"\1 Dict[str, Any]\3"),
            # 变量类型注解：: Dict 或 : dict
            (r"(:\s*)(Dict|dict)(\s*[=\n,\)])", r"\1Dict[str, Any]\3"),
            # Union类型：Dict | 或 dict |
            (r"(Dict|dict)(\s*\|)", r"Dict[str, Any]\2"),
            # Union类型：| Dict 或 | dict
            (r"(\|\s*)(Dict|dict)(\s*[,\)\n])", r"\1Dict[str, Any]\3"),
            # 括号中：(Dict) 或 (dict)
            (r"(\()(Dict|dict)(\))", r"\1Dict[str, Any]\3"),
        ]

        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)

        # 标记需要导入
        if "Dict[str, Any]" in content:
            self.required_imports.add("Dict")
            self.required_imports.add("Any")

        return content

    def fix_set_types(self, content: str) -> str:
        """
        修复Set/set类型参数

        将 Set 或 set 转换为 Set[Any]

        Args:
            content: 文件内容

        Returns:
            修复后的内容
        """
        patterns = [
            # 返回类型注解：-> Set 或 -> set
            (r"(->)\s+(Set|set)(\s*[:\n,\)])", r"\1 Set[Any]\3"),
            # 变量类型注解：: Set 或 : set
            (r"(:\s*)(Set|set)(\s*[=\n,\)])", r"\1Set[Any]\3"),
            # Union类型：Set | 或 set |
            (r"(Set|set)(\s*\|)", r"Set[Any]\2"),
            # Union类型：| Set 或 | set
            (r"(\|\s*)(Set|set)(\s*[,\)\n])", r"\1Set[Any]\3"),
            # 括号中：(Set) 或 (set)
            (r"(\()(Set|set)(\))", r"\1Set[Any]\3"),
        ]

        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)

        # 标记需要导入
        if "Set[Any]" in content:
            self.required_imports.add("Set")
            self.required_imports.add("Any")

        return content

    def fix_tuple_types(self, content: str) -> str:
        """
        修复Tuple/tuple类型参数

        将 Tuple 或 tuple 转换为 Tuple[Any, ...]

        Args:
            content: 文件内容

        Returns:
            修复后的内容
        """
        patterns = [
            # 返回类型注解：-> Tuple 或 -> tuple
            (r"(->)\s+(Tuple|tuple)(\s*[:\n,\)])", r"\1 Tuple[Any, ...]\3"),
            # 变量类型注解：: Tuple 或 : tuple
            (r"(:\s*)(Tuple|tuple)(\s*[=\n,\)])", r"\1Tuple[Any, ...]\3"),
            # Union类型：Tuple | 或 tuple |
            (r"(Tuple|tuple)(\s*\|)", r"Tuple[Any, ...]\2"),
            # Union类型：| Tuple 或 | tuple
            (r"(\|\s*)(Tuple|tuple)(\s*[,\)\n])", r"\1Tuple[Any, ...]\3"),
            # 括号中：(Tuple) 或 (tuple)
            (r"(\()(Tuple|tuple)(\))", r"\1Tuple[Any, ...]\3"),
        ]

        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)

        # 标记需要导入
        if "Tuple[Any, ...]" in content:
            self.required_imports.add("Tuple")
            self.required_imports.add("Any")

        return content

    def _add_missing_imports(self, content: str) -> str:
        """
        添加缺失的typing导入

        Args:
            content: 文件内容

        Returns:
            添加导入后的内容
        """
        if not self.required_imports:
            return content

        lines = content.split("\n")

        # 查找现有的typing导入
        typing_import_idx = -1
        existing_imports: set[str] = set()

        for idx, line in enumerate(lines):
            # 匹配 from typing import ...
            if line.strip().startswith("from typing import"):
                typing_import_idx = idx
                # 提取已有的导入
                import_part = line.split("import", 1)[1]
                # 处理括号形式的导入
                if "(" in import_part:
                    # 多行导入，需要找到结束位置
                    end_idx = idx
                    while end_idx < len(lines) and ")" not in lines[end_idx]:
                        end_idx += 1
                    # 合并多行
                    full_import = " ".join(lines[idx : end_idx + 1])
                    import_part = full_import.split("import", 1)[1]

                # 移除括号和空白
                import_part = import_part.replace("(", "").replace(")", "")
                # 分割导入项
                for item in import_part.split(","):
                    item = item.strip()
                    if item:
                        existing_imports.add(item)
                break

        # 计算需要添加的导入
        missing_imports = self.required_imports - existing_imports

        if not missing_imports:
            return content

        # 如果找到了typing导入，添加到现有导入中
        if typing_import_idx >= 0:
            line = lines[typing_import_idx]

            # 处理单行导入
            if "(" not in line:
                # 简单添加
                import_part = line.split("import", 1)[1].strip()
                all_imports = sorted(list(existing_imports | missing_imports))
                lines[typing_import_idx] = f"from typing import {', '.join(all_imports)}"
            else:
                # 多行导入，找到结束位置
                end_idx = typing_import_idx
                while end_idx < len(lines) and ")" not in lines[end_idx]:
                    end_idx += 1

                # 重建导入
                all_imports = sorted(list(existing_imports | missing_imports))
                new_import = f"from typing import {', '.join(all_imports)}"

                # 替换旧的多行导入
                lines[typing_import_idx : end_idx + 1] = [new_import]
        else:
            # 没有找到typing导入，添加新的导入
            # 找到合适的位置（在from __future__ import之后，其他导入之前）
            insert_idx = 0

            for idx, line in enumerate(lines):
                if line.strip().startswith("from __future__ import"):
                    insert_idx = idx + 1
                elif line.strip().startswith("import ") or line.strip().startswith("from "):
                    if insert_idx == 0:
                        insert_idx = idx
                    break

            # 插入新的导入
            all_imports = sorted(list(missing_imports))
            new_import = f"from typing import {', '.join(all_imports)}"
            lines.insert(insert_idx, new_import)

        return "\n".join(lines)

    def _count_fixes(self, original: str, fixed: str) -> int:
        """
        统计修复的数量

        Args:
            original: 原始内容
            fixed: 修复后的内容

        Returns:
            修复数量
        """
        count = 0

        # 统计添加的类型参数
        count += fixed.count("List[Any]") - original.count("List[Any]")
        count += fixed.count("Dict[str, Any]") - original.count("Dict[str, Any]")
        count += fixed.count("Set[Any]") - original.count("Set[Any]")
        count += fixed.count("Tuple[Any, ...]") - original.count("Tuple[Any, ...]")

        return count
