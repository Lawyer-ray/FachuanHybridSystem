#!/usr/bin/env python3
"""
清理 mypy.ini 中不必要的 ignore_errors 条目
目标: 只保留 migrations + admin (≤10 个条目)
"""

from pathlib import Path

def cleanup_mypy_ini():
    mypy_ini = Path("mypy.ini")
    content = mypy_ini.read_text()
    
    # 保留的核心 ignore_errors (migrations + admin + tests + conftest)
    keep_sections = [
        "[mypy-*.migrations.*]",
        "[mypy-*.admin.*]",
        "[mypy-*.tests.*]",
        "[mypy-tests.*]",
        "[mypy-conftest]",
        "[mypy-apps.*.models]",
        "[mypy-apps.*.models.*]",
    ]
    
    lines = content.split('\n')
    new_lines = []
    skip_until_next_section = False
    current_section = None
    
    for i, line in enumerate(lines):
        # 检测新的 section
        if line.strip().startswith('[mypy-'):
            current_section = line.strip()
            skip_until_next_section = False
            
            # 检查是否是要保留的 section
            is_keep_section = any(keep in current_section for keep in keep_sections)
            
            if is_keep_section:
                new_lines.append(line)
            else:
                # 检查下一行是否是 ignore_errors = True
                if i + 1 < len(lines) and lines[i + 1].strip() == "ignore_errors = True":
                    skip_until_next_section = True
                    continue
                else:
                    new_lines.append(line)
        elif line.strip() == "ignore_errors = True" and skip_until_next_section:
            # 跳过这个 ignore_errors
            continue
        elif skip_until_next_section and line.strip() == "":
            # 跳过空行
            continue
        elif line.strip().startswith('#') and skip_until_next_section:
            # 跳过注释
            continue
        else:
            skip_until_next_section = False
            new_lines.append(line)
    
    # 清理多余的空行
    cleaned_lines = []
    prev_empty = False
    for line in new_lines:
        if line.strip() == "":
            if not prev_empty:
                cleaned_lines.append(line)
            prev_empty = True
        else:
            cleaned_lines.append(line)
            prev_empty = False
    
    # 写回文件
    mypy_ini.write_text('\n'.join(cleaned_lines))
    
    # 统计剩余的 ignore_errors
    remaining = cleaned_lines.count("ignore_errors = True")
    print(f"✅ 清理完成")
    print(f"📊 剩余 ignore_errors: {remaining} 个")
    print(f"🎯 目标: ≤10 个")
    
    if remaining <= 10:
        print("✅ 达到目标!")
    else:
        print(f"⚠️  还需要减少 {remaining - 10} 个")

if __name__ == "__main__":
    cleanup_mypy_ini()
