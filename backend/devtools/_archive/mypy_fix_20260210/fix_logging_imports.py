#!/usr/bin/env python3
"""
修复错误放置的 import logging 语句
这些语句被错误地插入到了 try 块中间
"""

import re
from pathlib import Path


def fix_file(filepath: Path) -> bool:
    """修复单个文件中的 logging import 问题"""
    content = filepath.read_text(encoding='utf-8')
    original_content = content
    
    # 检查文件顶部是否已有 import logging
    has_logging_import = bool(re.search(r'^import logging$', content, re.MULTILINE))
    has_logger_def = bool(re.search(r'^logger = logging\.getLogger', content, re.MULTILINE))
    
    # 移除所有错误放置的 import logging 和 logger 定义
    # 这些通常出现在 try 块中间或其他不合适的位置
    lines = content.split('\n')
    fixed_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 跳过单独的 import logging 行（如果前后有空行或在 try 块中）
        if line.strip() == 'import logging':
            # 检查是否在不合适的位置（不是在文件顶部的 import 区域）
            if i > 20 or (i > 0 and not lines[i-1].strip().startswith('import')):
                # 跳过这行和后面的空行
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                # 跳过紧跟的 logger 定义
                if i < len(lines) and lines[i].strip().startswith('logger = logging.getLogger'):
                    i += 1
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                continue
        
        # 跳过单独的 logger 定义行（如果在不合适的位置）
        if line.strip().startswith('logger = logging.getLogger'):
            if i > 30:  # 不在文件顶部
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue
        
        fixed_lines.append(line)
        i += 1
    
    content = '\n'.join(fixed_lines)
    
    # 如果文件顶部没有 import logging，添加它
    if not has_logging_import:
        # 找到最后一个 import 语句的位置
        lines = content.split('\n')
        last_import_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('import ') or line.strip().startswith('from '):
                last_import_idx = i
        
        if last_import_idx >= 0:
            # 在最后一个 import 后添加 import logging
            lines.insert(last_import_idx + 1, 'import logging')
            content = '\n'.join(lines)
    
    # 如果文件没有 logger 定义，添加它
    if not has_logger_def:
        # 在 import 区域后添加 logger 定义
        lines = content.split('\n')
        last_import_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('import ') or line.strip().startswith('from '):
                last_import_idx = i
        
        if last_import_idx >= 0:
            # 找到 import 区域后的第一个空行
            insert_idx = last_import_idx + 1
            while insert_idx < len(lines) and (lines[insert_idx].strip().startswith('import') or lines[insert_idx].strip().startswith('from')):
                insert_idx += 1
            
            # 添加空行和 logger 定义
            if insert_idx < len(lines) and lines[insert_idx].strip():
                lines.insert(insert_idx, '')
                insert_idx += 1
            lines.insert(insert_idx, '')
            lines.insert(insert_idx + 1, 'logger = logging.getLogger(__name__)')
            content = '\n'.join(lines)
    
    if content != original_content:
        filepath.write_text(content, encoding='utf-8')
        return True
    return False


def main():
    """主函数"""
    backend_dir = Path(__file__).parent
    
    # 需要修复的文件列表（从 grep 结果中提取）
    files_to_fix = [
        'apps/automation/services/chat/feishu_provider.py',
        'apps/contracts/services/lawyer_assignment_service.py',
        'apps/contracts/services/contract_service.py',
        'apps/chat_records/services/recording_service.py',
        'apps/chat_records/services/video_frame_extract_service.py',
        'apps/chat_records/services/frame_selection_service.py',
        'apps/chat_records/services/export_service.py',
        'apps/chat_records/services/screenshot_service.py',
        'apps/contracts/services/admin_actions/contract_admin_action_service.py',
        'apps/contracts/services/supplementary/supplementary_agreement_service.py',
        'apps/contracts/services/assignment/filing_number_service.py',
        'apps/contracts/services/assignment/lawyer_assignment_service.py',
        'apps/contracts/services/supplementary_agreement_service.py',
        'apps/contracts/services/folder/folder_binding_service.py',
        'apps/contracts/services/folder/contract_subdir_path_resolver.py',
        'apps/contracts/services/payment/contract_finance_mutation_service.py',
        'apps/contracts/services/contract/contract_display_service.py',
        'apps/contracts/services/contract/contract_admin_service.py',
        'apps/contracts/services/contract/contract_service.py',
        'apps/contracts/services/contract/supplementary_agreement_query_service.py',
        'apps/contracts/services/contract/contract_template_cache.py',
        'apps/contracts/services/contract/contract_service_adapter.py',
        'apps/contracts/schemas.py',
        'apps/contracts/api/contract_api.py',
        'apps/contracts/services/contract/contract_admin_mutation_service.py',
        'apps/contracts/services/contract/contract_mutation_service.py',
        'apps/contracts/schemas/base.py',
        'apps/contracts/schemas/contract_schemas.py',
        'apps/contracts/api/folder_binding_api.py',
        'apps/contracts/admin/contract_forms_admin.py',
        'apps/contracts/admin/mixins/display_mixin.py',
        'apps/contracts/admin/mixins/save_mixin.py',
        'apps/contracts/admin/mixins/action_mixin.py',
        'apps/chat_records/schemas.py',
        'apps/chat_records/tasks.py',
        'apps/reminders/services/reminder_service_adapter.py',
        'apps/documents/api/preservation_materials_api.py',
        'apps/documents/api/document_api.py',
        'apps/documents/api/placeholder_api.py',
        'apps/documents/api/folder_template_api.py',
        'apps/documents/api/litigation_generation_api.py',
        'apps/documents/services/document_service_adapter.py',
        'apps/documents/services/code_placeholder_autodiscover.py',
        'apps/documents/services/template_matching_service.py',
        'apps/documents/services/code_placeholder_catalog_service.py',
        'apps/documents/services/generation/path_utils.py',
        'apps/documents/services/document_template/placeholder_extractor.py',
        'apps/documents/services/generation/folder_generation_service.py',
        'apps/documents/services/generation/generators/contract_generator.py',
        'apps/documents/services/generation/prompt_version_service.py',
        'apps/documents/services/generation/generation_task_service.py',
    ]
    
    fixed_count = 0
    for file_path in files_to_fix:
        full_path = backend_dir / file_path
        if full_path.exists():
            try:
                if fix_file(full_path):
                    print(f"✓ 修复: {file_path}")
                    fixed_count += 1
                else:
                    print(f"- 跳过: {file_path} (无需修复)")
            except Exception as e:
                print(f"✗ 错误: {file_path} - {e}")
        else:
            print(f"✗ 文件不存在: {file_path}")
    
    print(f"\n总计修复 {fixed_count} 个文件")


if __name__ == '__main__':
    main()
