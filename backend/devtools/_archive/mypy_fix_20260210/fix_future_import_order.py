#!/usr/bin/env python3
"""修复 import logging 在 from __future__ 之前的问题"""
import re

files = [
    "apps/contracts/services/folder/folder_binding_service.py",
    "apps/contracts/api/folder_binding_api.py",
    "apps/contracts/services/folder/contract_subdir_path_resolver.py",
    "apps/contracts/services/assignment/filing_number_service.py",
    "apps/documents/api/folder_template_api.py",
    "apps/documents/api/placeholder_api.py",
    "apps/documents/api/document_api.py",
    "apps/documents/services/template_matching_service.py",
    "apps/documents/services/document_service_adapter.py",
    "apps/documents/services/generation/prompt_version_service.py",
    "apps/chat_records/tasks.py",
]

for filepath in files:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查是否有问题
        if "from __future__" not in content or "import logging" not in content:
            continue

        lines = content.split("\n")
        future_idx = -1
        logging_idx = -1

        for i, line in enumerate(lines):
            if line.strip().startswith("from __future__"):
                future_idx = i
            if line.strip() == "import logging":
                logging_idx = i
                break

        if future_idx == -1 or logging_idx == -1:
            continue

        if logging_idx < future_idx:
            # 移除 import logging
            lines.pop(logging_idx)

            # 在 from __future__ 之后找到合适的位置插入
            # 跳过 from __future__ 和紧随的文档字符串
            insert_idx = future_idx

            # 如果 from __future__ 后面是文档字符串，跳过它
            i = future_idx + 1
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    # 找到文档字符串结束
                    quote = stripped[:3]
                    if stripped.endswith(quote) and len(stripped) > 6:
                        insert_idx = i + 1
                        break
                    else:
                        # 多行文档字符串
                        i += 1
                        while i < len(lines):
                            if lines[i].strip().endswith(quote):
                                insert_idx = i + 1
                                break
                            i += 1
                        break
                elif stripped == "" or stripped.startswith("#"):
                    i += 1
                    continue
                else:
                    insert_idx = i
                    break

            # 插入 import logging
            lines.insert(insert_idx, "import logging")

            new_content = "\n".join(lines)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)

            print(f"✓ 修复 {filepath}")

    except Exception as e:
        print(f"✗ 错误 {filepath}: {e}")

print("\n完成")
