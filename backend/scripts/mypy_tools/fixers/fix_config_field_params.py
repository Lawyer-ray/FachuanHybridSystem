#!/usr/bin/env python3
"""修复 ConfigField 参数名"""
from pathlib import Path
import re

file_path = Path("apps/core/config/migrator_schema_registry.py")
content = file_path.read_text()

# 替换 key= 为 name=
content = re.sub(r"key='([^']+)'", r"name='\1'", content)

# 替换 field_type= 为 type=，并转换类型字符串为类型对象
type_mapping = {
    "'string'": "str",
    "'boolean'": "bool",
    "'list'": "list",
    "'dict'": "dict",
    "'int'": "int",
    "'float'": "float",
}

for old_type, new_type in type_mapping.items():
    content = content.replace(f"field_type={old_type}", f"type={new_type}")

file_path.write_text(content)
print(f"已修复 {file_path}")
