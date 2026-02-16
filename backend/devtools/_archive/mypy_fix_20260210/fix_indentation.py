#!/usr/bin/env python3
"""修复嵌套函数定义后的缩进问题"""
import re
from pathlib import Path

def fix_file_indentation(file_path: Path) -> bool:
    """修复文件中的所有缩进问题"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        lines = content.split('\n')
        fixed_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # 检查是否是嵌套函数定义（8个空格开头）
            if re.match(r'^        def \w+\([^)]*\)', line):
                fixed_lines.append(line)
                i += 1
                
                # 检查下一行是否需要修复缩进
                if i < len(lines):
                    next_line = lines[i]
                    # 如果下一行是8个空格开头（应该是12个）
                    if next_line.startswith('        ') and not next_line.startswith('            '):
                        # 添加4个空格
                        fixed_lines.append('    ' + next_line)
                        i += 1
                        
                        # 继续修复后续行，直到遇到正确缩进或空行
                        while i < len(lines):
                            curr_line = lines[i]
                            if not curr_line.strip():  # 空行
                                fixed_lines.append(curr_line)
                                i += 1
                                break
                            elif curr_line.startswith('            '):  # 已经是正确缩进
                                fixed_lines.append(curr_line)
                                i += 1
                                break
                            elif curr_line.startswith('        ') and not curr_line.startswith('            '):
                                # 需要修复的行
                                fixed_lines.append('    ' + curr_line)
                                i += 1
                            else:
                                # 其他情况，停止修复
                                fixed_lines.append(curr_line)
                                i += 1
                                break
                    else:
                        continue
            else:
                fixed_lines.append(line)
                i += 1
        
        new_content = '\n'.join(fixed_lines)
        
        if new_content != original:
            file_path.write_text(new_content, encoding='utf-8')
            return True
        return False
    except Exception as e:
        print(f"处理 {file_path} 时出错: {e}")
        return False

def main():
    """主函数"""
    # 指定需要修复的文件
    files_to_fix = [
        'apps/automation/services/sms/attachment_query_service.py',
        'apps/automation/services/sms/attachment_upload_service.py',
        'apps/documents/services/generation_service.py',
        'apps/documents/services/pdf_merge_service.py',
        'apps/documents/services/placeholders/authorization_materials/power_of_attorney_service.py',
    ]
    
    fixed_count = 0
    for file_path_str in files_to_fix:
        file_path = Path(file_path_str)
        if file_path.exists():
            if fix_file_indentation(file_path):
                print(f"已修复: {file_path}")
                fixed_count += 1
        else:
            print(f"文件不存在: {file_path}")
    
    print(f"\n总共修复了 {fixed_count} 个文件")

if __name__ == '__main__':
    main()
