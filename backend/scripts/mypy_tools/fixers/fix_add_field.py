#!/usr/bin/env python3
"""批量替换 schema.add_field 为 schema.register"""
from pathlib import Path

file_path = Path("apps/core/config/migrator_schema_registry.py")
content = file_path.read_text()
content = content.replace("schema.add_field(", "schema.register(")
file_path.write_text(content)
print(f"已修复 {file_path}")
