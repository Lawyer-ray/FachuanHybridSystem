"""批量修复 name-defined 错误 - 添加 TYPE_CHECKING 导入"""

import re
import subprocess
from pathlib import Path
from typing import Dict, Set, List

backend_path = Path(__file__).parent.parent

# 常见类型到导入路径的映射
TYPE_IMPORT_MAP = {
    "ICaseService": "from apps.core.interfaces import ICaseService",
    "IClientService": "from apps.core.interfaces import IClientService",
    "ILawyerService": "from apps.core.interfaces import ILawyerService",
    "ICaseChatService": "from apps.core.interfaces import ICaseChatService",
    "CourtSMS": "from apps.automation.models import CourtSMS",
    "CaseChat": "from apps.cases.models import CaseChat",
    "ClientService": "from apps.client.services import ClientService",
    "ClientIdentityDocService": "from apps.client.services import ClientIdentityDocService",
    "LawyerAssignmentService": "from apps.contracts.services import LawyerAssignmentService",
    "ContractPayment": "from apps.contracts.models import ContractPayment",
    "DocumentRenamer": "from .document_renamer import DocumentRenamer",
    "DocumentAttachmentService": "from .document_attachment_service import DocumentAttachmentService",
    "SMSNotificationService": "from .sms_notification_service import SMSNotificationService",
    "CaseNumberExtractorService": "from .case_number_extractor import CaseNumberExtractorService",
    "ValidationException": "from apps.core.exceptions import ValidationException",
    "BusinessException": "from apps.core.exceptions import BusinessException",
    "CaptchaRecognizer": "from ..captcha.captcha_recognition_service import CaptchaRecognizer",
    "TokenService": "from ..scraper.core.token_service import TokenService",
    "BrowserConfig": "from ..scraper.core.browser_manager import BrowserConfig",
}


def get_name_defined_errors_by_file() -> Dict[str, Set[str]]:
    """获取每个文件的 name-defined 错误"""
    result = subprocess.run(
        ["mypy", "--strict", "apps/"],
        cwd=backend_path,
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    
    file_errors = {}
    for line in output.split('\n'):
        match = re.match(r'(apps/[^:]+):\d+:\d+: error: Name "([^"]+)" is not defined\s+\[name-defined\]', line)
        if match:
            file_path = match.group(1)
            class_name = match.group(2)
            
            if file_path not in file_errors:
                file_errors[file_path] = set()
            file_errors[file_path].add(class_name)
    
    return file_errors


def add_type_checking_imports(file_path: str, missing_types: Set[str]) -> bool:
    """添加 TYPE_CHECKING 导入到文件"""
    try:
        full_path = backend_path / file_path
        if not full_path.exists():
            return False
        
        content = full_path.read_text(encoding="utf-8")
        lines = content.split('\n')
        
        # 过滤出我们知道如何导入的类型
        known_types = {t for t in missing_types if t in TYPE_IMPORT_MAP}
        if not known_types:
            return False
        
        # 检查是否已有 TYPE_CHECKING
        has_type_checking = 'TYPE_CHECKING' in content
        type_checking_line = -1
        
        if has_type_checking:
            # 找到 TYPE_CHECKING 块
            for i, line in enumerate(lines):
                if 'if TYPE_CHECKING:' in line:
                    type_checking_line = i
                    break
        
        # 找到导入区域的末尾
        last_import_line = 0
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                last_import_line = i
        
        if not has_type_checking:
            # 需要添加 TYPE_CHECKING 到 typing 导入
            for i, line in enumerate(lines):
                if 'from typing import' in line and 'TYPE_CHECKING' not in line:
                    # 添加 TYPE_CHECKING
                    if '(' in line:
                        # 多行导入
                        lines[i] = line.replace(')', ', TYPE_CHECKING)')
                    else:
                        lines[i] = line.rstrip() + ', TYPE_CHECKING'
                    has_type_checking = True
                    break
            
            if not has_type_checking:
                # 没有 typing 导入，添加一个
                lines.insert(last_import_line + 1, 'from typing import TYPE_CHECKING')
                last_import_line += 1
                has_type_checking = True
        
        # 添加 TYPE_CHECKING 块
        if type_checking_line == -1:
            # 创建新的 TYPE_CHECKING 块
            insert_lines = ['', 'if TYPE_CHECKING:']
            for type_name in sorted(known_types):
                import_stmt = TYPE_IMPORT_MAP[type_name]
                insert_lines.append(f'    {import_stmt}')
            
            lines = lines[:last_import_line + 1] + insert_lines + lines[last_import_line + 1:]
        else:
            # 在现有 TYPE_CHECKING 块中添加
            # 找到块的结束位置
            block_end = type_checking_line + 1
            for i in range(type_checking_line + 1, len(lines)):
                if lines[i] and not lines[i].startswith(' ') and not lines[i].startswith('\t'):
                    block_end = i
                    break
            
            # 检查哪些类型还没导入
            existing_imports = '\n'.join(lines[type_checking_line:block_end])
            new_types = []
            for type_name in sorted(known_types):
                if type_name not in existing_imports:
                    import_stmt = TYPE_IMPORT_MAP[type_name]
                    new_types.append(f'    {import_stmt}')
            
            if new_types:
                lines = lines[:block_end] + new_types + lines[block_end:]
        
        full_path.write_text('\n'.join(lines), encoding="utf-8")
        print(f"✓ 修复 {file_path}")
        print(f"  添加: {', '.join(sorted(known_types))}")
        return True
        
    except Exception as e:
        print(f"✗ 修复失败 {file_path}: {e}")
        return False


def main():
    print("=" * 80)
    print("批量修复 name-defined 错误")
    print("=" * 80)
    
    file_errors = get_name_defined_errors_by_file()
    print(f"\n找到 {len(file_errors)} 个文件有 name-defined 错误\n")
    
    fixed = 0
    for file_path, missing_types in sorted(file_errors.items())[:20]:  # 只处理前20个
        print(f"\n处理: {file_path}")
        print(f"缺失: {', '.join(sorted(missing_types))}")
        if add_type_checking_imports(file_path, missing_types):
            fixed += 1
    
    print(f"\n✅ 完成: 处理了 {fixed} 个文件")
    
    # 验证
    remaining = get_name_defined_errors_by_file()
    total_errors = sum(len(types) for types in remaining.values())
    print(f"剩余 name-defined 错误: {total_errors}")
    
    # 检查总错误数
    result = subprocess.run(
        ["mypy", "--strict", "apps/"],
        cwd=backend_path,
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    for line in output.split('\n'):
        if 'Found' in line and 'errors' in line:
            print(f"\n{line}")
            break


if __name__ == "__main__":
    main()
