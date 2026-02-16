#!/usr/bin/env python3
"""修复 migration_tracker.py 的类型注解"""
import re
from pathlib import Path

file_path = Path("apps/core/config/migration_tracker.py")
content = file_path.read_text()

# 查找所有 "Need type annotation" 的行号并修复
# 通常是 result = {}, data = {}, info = {} 等模式

# 修复 result = {} 模式
content = re.sub(
    r"(\s+)(result) = \{([^}]*)\}", lambda m: f"{m.group(1)}{m.group(2)}: Dict[str, Any] = {{{m.group(3)}}}", content
)

# 修复 data = {} 模式
content = re.sub(
    r"(\s+)(data) = \{([^}]*)\}", lambda m: f"{m.group(1)}{m.group(2)}: Dict[str, Any] = {{{m.group(3)}}}", content
)

# 修复 info = {} 模式
content = re.sub(
    r"(\s+)(info) = \{([^}]*)\}", lambda m: f"{m.group(1)}{m.group(2)}: Dict[str, Any] = {{{m.group(3)}}}", content
)

# 修复 stats = {} 模式
content = re.sub(
    r"(\s+)(stats) = \{([^}]*)\}", lambda m: f"{m.group(1)}{m.group(2)}: Dict[str, Any] = {{{m.group(3)}}}", content
)

# 修复 summary = {} 模式
content = re.sub(
    r"(\s+)(summary) = \{([^}]*)\}", lambda m: f"{m.group(1)}{m.group(2)}: Dict[str, Any] = {{{m.group(3)}}}", content
)

# 确保有 Dict, Any 导入
if "from typing import" in content:
    typing_line_match = re.search(r"from typing import ([^\n]+)", content)
    if typing_line_match:
        imports = typing_line_match.group(1)
        needed = []
        if "Dict" not in imports:
            needed.append("Dict")
        if "Any" not in imports:
            needed.append("Any")

        if needed:
            new_imports = imports.rstrip() + ", " + ", ".join(needed)
            content = content.replace(f"from typing import {imports}", f"from typing import {new_imports}")

file_path.write_text(content)
print(f"已修复 {file_path}")
