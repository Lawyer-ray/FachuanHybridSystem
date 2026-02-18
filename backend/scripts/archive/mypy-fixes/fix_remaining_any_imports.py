"""批量添加缺失的 Any 导入"""

import subprocess
from pathlib import Path

backend_path = Path(__file__).parent.parent

# 需要添加 Any 导入的文件列表
files_need_any = [
    "apps/core/management/commands/analyze_performance.py",
    "apps/automation/services/ai/ollama_client.py",
    "apps/automation/services/ai/moonshot_client.py",
    "apps/contracts/services/contract_reminder_service.py",
    "apps/automation/services/insurance/exceptions.py",
    "apps/automation/services/chat/owner_config_manager.py",
    "apps/cases/services/case_chat_service.py",
    "apps/organization/services/lawyer_service.py",
    "apps/organization/services/lawfirm_service.py",
]


def add_any_import(file_path: str) -> bool:
    """添加 Any 导入到文件"""
    try:
        full_path = backend_path / file_path
        if not full_path.exists():
            print(f"✗ 文件不存在: {file_path}")
            return False
        
        content = full_path.read_text(encoding="utf-8")
        lines = content.split('\n')
        
        # 检查是否已有 Any 导入
        if 'from typing import' in content and 'Any' in content:
            # 可能已经导入了，检查是否在同一行
            for i, line in enumerate(lines):
                if 'from typing import' in line and 'Any' not in line:
                    # 添加 Any 到现有的 typing 导入
                    if line.strip().endswith(','):
                        lines[i] = line.rstrip() + ' Any'
                    elif '(' in line:
                        # 多行导入
                        lines[i] = line.rstrip()[:-1] + ', Any)'
                    else:
                        lines[i] = line.rstrip() + ', Any'
                    
                    full_path.write_text('\n'.join(lines), encoding="utf-8")
                    print(f"✓ 添加 Any 到现有导入: {file_path}")
                    return True
        
        # 查找合适的位置插入 Any 导入
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith('from typing import'):
                # 在现有的 typing 导入行添加 Any
                if 'Any' not in line:
                    if line.strip().endswith(','):
                        lines[i] = line.rstrip() + ' Any'
                    else:
                        lines[i] = line.rstrip() + ', Any'
                    full_path.write_text('\n'.join(lines), encoding="utf-8")
                    print(f"✓ 添加 Any 到现有导入: {file_path}")
                    return True
                else:
                    print(f"- 已有 Any 导入: {file_path}")
                    return False
            elif line.startswith('import ') or line.startswith('from '):
                insert_pos = i + 1
        
        # 如果没有找到 typing 导入，在其他导入后添加
        if insert_pos > 0:
            lines.insert(insert_pos, 'from typing import Any')
            full_path.write_text('\n'.join(lines), encoding="utf-8")
            print(f"✓ 添加新的 Any 导入: {file_path}")
            return True
        
        print(f"✗ 无法确定插入位置: {file_path}")
        return False
        
    except Exception as e:
        print(f"✗ 处理失败 {file_path}: {e}")
        return False


def main():
    print("=" * 80)
    print("批量添加缺失的 Any 导入")
    print("=" * 80)
    
    fixed = 0
    for file_path in files_need_any:
        if add_any_import(file_path):
            fixed += 1
    
    print(f"\n✅ 完成: 处理了 {fixed} 个文件")
    
    # 验证
    result = subprocess.run(
        ["mypy", "--strict", "apps/"],
        cwd=backend_path,
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    
    # 统计剩余的 name-defined 错误
    name_defined_count = output.count('[name-defined]')
    print(f"剩余 name-defined 错误: {name_defined_count}")
    
    # 检查总错误数
    for line in output.split('\n'):
        if 'Found' in line and 'errors' in line:
            print(f"\n{line}")
            break


if __name__ == "__main__":
    main()
