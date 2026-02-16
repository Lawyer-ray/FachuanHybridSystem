#!/usr/bin/env python3
"""修复litigation_ai模块的复杂类型错误"""

import re
from pathlib import Path
from typing import Any


def fix_ocr_service(file_path: Path) -> bool:
    """修复OCR服务的特定错误"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 添加缺失的方法
    if '_to_list' not in content and 'def _get_position_key' in content:
        # 在_get_position_key方法前添加_to_list方法
        to_list_method = '''
    def _to_list(self, x: Any) -> list[Any]:
        """将各种类型转换为列表"""
        if x is None:
            return []
        if hasattr(x, 'tolist'):
            tolist = getattr(x, "tolist", None)
            if callable(tolist):
                return tolist()
        if isinstance(x, (list, tuple)):
            return list(x)
        return [x]

'''
        content = content.replace(
            '    def _get_position_key',
            to_list_method + '    def _get_position_key'
        )
    
    # 添加_is_timestamp_text方法
    if '_is_timestamp_text' not in content and 'def _get_position_key' in content:
        timestamp_method = '''
    def _is_timestamp_text(self, text: str) -> bool:
        """判断是否为时间戳文本"""
        if not text:
            return False
        if re.match(r"^\\d{1,2}:\\d{2}$", text):
            return True
        if re.match(r"^\\d{1,4}[-/]\\d{1,2}[-/]\\d{1,2}$", text):
            return True
        if re.match(r"^\\d{1,2}月\\d{1,2}日$", text):
            return True
        return False

'''
        # 在_get_position_key方法后添加
        content = re.sub(
            r'(    def _get_position_key.*?\n(?:        .*\n)*)',
            r'\1' + timestamp_method,
            content,
            count=1
        )
    
    # 修复_get_position_key方法中的box和text参数
    content = re.sub(
        r'def _get_position_key\(self, box\):',
        'def _get_position_key(self, box: list[Any]) -> tuple[float, float]:',
        content
    )
    
    # 修复方法体中的变量定义
    if 'if not box:' in content and 'return (0.0, 0.0)' not in content:
        content = re.sub(
            r'if not box:\s*return',
            'if not box:\n            return (0.0, 0.0)',
            content
        )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_sms_stages(file_path: Path) -> bool:
    """修复SMS stages中的attr-defined错误"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 添加cast导入
    if 'from typing import cast' not in content and 'sms.id' in content:
        if 'from typing import' in content:
            content = re.sub(
                r'(from typing import [^\n]+)',
                r'\1, cast',
                content,
                count=1
            )
        else:
            content = 'from typing import cast\n' + content
    
    # 修复sms.id访问
    content = re.sub(r'\bsms\.id\b', 'cast(int, sms.id)', content)
    content = re.sub(r'\btask\.id\b', 'cast(int, task.id)', content)
    content = re.sub(r'\bscraper_task\.id\b', 'cast(int, scraper_task.id)', content)
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_task_recovery_service(file_path: Path) -> bool:
    """修复task recovery service"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 添加cast导入
    if 'from typing import cast' not in content:
        if 'from typing import' in content:
            content = re.sub(
                r'(from typing import [^\n]+)',
                r'\1, cast',
                content,
                count=1
            )
        else:
            content = 'from typing import cast\n' + content
    
    # 修复result字典类型
    content = re.sub(
        r'result\s*=\s*\{',
        'result: dict[str, Any] = {',
        content
    )
    
    # 修复sms.id和task.id访问
    content = re.sub(r'\btask\.id\b', 'cast(int, task.id)', content)
    content = re.sub(r'\bsms\.id\b', 'cast(int, sms.id)', content)
    content = re.sub(r'\bsms\.scraper_task\.status\b', 'cast(Any, sms.scraper_task).status', content)
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_contract_workflows(file_path: Path) -> bool:
    """修复contract workflows中的attr-defined错误"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 添加cast导入
    if 'from typing import cast' not in content and 'source_contract.' in content:
        if 'from typing import' in content:
            content = re.sub(
                r'(from typing import [^\n]+)',
                r'\1, cast',
                content,
                count=1
            )
        else:
            content = 'from typing import cast, Any\n' + content
    
    # 修复关联字段访问
    content = re.sub(
        r'source_contract\.contract_parties\.all\(\)',
        'cast(Any, source_contract.contract_parties).all()',
        content
    )
    content = re.sub(
        r'source_contract\.assignments\.all\(\)',
        'cast(Any, source_contract.assignments).all()',
        content
    )
    content = re.sub(
        r'source_contract\.reminders\.all\(\)',
        'cast(Any, source_contract.reminders).all()',
        content
    )
    content = re.sub(
        r'source_contract\.supplementary_agreements\.all\(\)',
        'cast(Any, source_contract.supplementary_agreements).all()',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_schemas_return_types(file_path: Path) -> bool:
    """修复schemas中的返回类型错误"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复from_model返回类型
    content = re.sub(
        r'def from_model\(cls, obj: Any\) -> "from":',
        'def from_model(cls, obj: Any) -> "CourtSMSDetailSchema":',
        content
    )
    
    # 修复PreservationQuoteSchema返回类型
    if 'PreservationQuoteCreateSchema' in content and 'PreservationQuoteSchema' in content:
        content = re.sub(
            r'(\s+def from_dict\(cls.*?\) -> )PreservationQuoteCreateSchema:',
            r'\1"PreservationQuoteSchema":',
            content
        )
        content = re.sub(
            r'(\s+def from_api_response\(cls.*?\) -> )PreservationQuoteCreateSchema:',
            r'\1"QuoteListItemSchema":',
            content
        )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_image_rotation_schema(file_path: Path) -> bool:
    """修复image rotation schema"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复valid_sizes类型
    content = re.sub(
        r'valid_sizes=\{\}',
        'valid_sizes: tuple[str, ...] = ("A4", "A3", "B4", "B5")',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_core_cache(file_path: Path) -> bool:
    """修复core cache"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复_safe_get_config函数签名
    content = re.sub(
        r'def _safe_get_config\(key, default=None\) -> Any:',
        'def _safe_get_config(key: str, default: Any = None) -> Any:',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_file_utils(file_path: Path) -> bool:
    """修复file utils"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复result变量类型注解
    content = re.sub(
        r'result = \{"valid": True, "error": None, "info": \{\}\}',
        'result: dict[str, Any] = {"valid": True, "error": None, "info": {}}',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_anti_detection(file_path: Path) -> bool:
    """修复anti detection"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 为page参数添加类型注解
    content = re.sub(
        r'def inject_stealth_script\(page\) -> None:',
        'def inject_stealth_script(page: Any) -> None:',
        content
    )
    content = re.sub(
        r'def human_like_typing\(page, selector: str, text: str, delay_range=',
        'def human_like_typing(page: Any, selector: str, text: str, delay_range: tuple[float, float] = ',
        content
    )
    content = re.sub(
        r'def random_mouse_move\(page\) -> None:',
        'def random_mouse_move(page: Any) -> None:',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_captcha_services(file_path: Path) -> bool:
    """修复captcha services"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 为page参数添加类型注解
    content = re.sub(
        r'def recognize_from_element\(self, page, selector: str\)',
        'def recognize_from_element(self, page: Any, selector: str)',
        content
    )
    
    # 添加cast来修复no-any-return
    if 'from typing import cast' not in content and 'return result' in content:
        if 'from typing import' in content:
            content = re.sub(
                r'(from typing import [^\n]+)',
                r'\1, cast',
                content,
                count=1
            )
        else:
            content = 'from typing import cast\n' + content
    
    # 修复return result
    content = re.sub(
        r'return result$',
        'return cast(str, result)',
        content,
        flags=re.MULTILINE
    )
    content = re.sub(
        r'return cleaned_result$',
        'return cast(str, cleaned_result)',
        content,
        flags=re.MULTILINE
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_ollama_config(file_path: Path) -> bool:
    """修复ollama config"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 添加cast
    if 'from typing import cast' not in content:
        if 'from typing import' in content:
            content = re.sub(
                r'(from typing import [^\n]+)',
                r'\1, cast',
                content,
                count=1
            )
        else:
            content = 'from typing import cast\n' + content
    
    # 修复return语句
    content = re.sub(
        r"return ollama_config\.get\('MODEL', cls\.DEFAULT_MODEL\)",
        "return cast(str, ollama_config.get('MODEL', cls.DEFAULT_MODEL))",
        content
    )
    content = re.sub(
        r"return ollama_config\.get\('BASE_URL', cls\.DEFAULT_BASE_URL\)",
        "return cast(str, ollama_config.get('BASE_URL', cls.DEFAULT_BASE_URL))",
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_core_schemas(file_path: Path) -> bool:
    """修复core schemas"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 添加cast
    if 'from typing import cast' not in content:
        if 'from typing import' in content:
            content = re.sub(
                r'(from typing import [^\n]+)',
                r'\1, cast',
                content,
                count=1
            )
        else:
            content = 'from typing import cast\n' + content
    
    # 修复return value
    content = re.sub(
        r'(\s+)return value$',
        r'\1return cast(datetime, value)',
        content,
        flags=re.MULTILINE
    )
    content = re.sub(
        r'(\s+)return getter\(\)$',
        r'\1return cast(str, getter())',
        content,
        flags=re.MULTILINE
    )
    content = re.sub(
        r'(\s+)return file_field\.url$',
        r'\1return cast(str, file_field.url)',
        content,
        flags=re.MULTILINE
    )
    content = re.sub(
        r'(\s+)return file_field\.path$',
        r'\1return cast(str, file_field.path)',
        content,
        flags=re.MULTILINE
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_exceptions_factory(file_path: Path) -> bool:
    """修复exceptions factory"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复RecognitionTimeoutError引用
    if 'RecognitionTimeoutError' in content and 'class RecognitionTimeoutError' not in content:
        # 添加前向引用
        content = re.sub(
            r'-> "RecognitionTimeoutError":',
            r'-> "AutomationException":',
            content
        )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_document_delivery_schema(file_path: Path) -> bool:
    """修复document delivery schema"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复send_time参数
    content = re.sub(
        r'send_time=send_time,',
        'send_time=send_time if send_time else datetime.now(),',
        content
    )
    
    # 确保导入datetime
    if 'from datetime import datetime' not in content and 'datetime.now()' in content:
        content = 'from datetime import datetime\n' + content
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_folder_validation(file_path: Path) -> bool:
    """修复folder validation service"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复重复定义的path变量
    content = re.sub(
        r'(\s+)path: list\[Any\] = \[\](\s+# 递归验证子节点)',
        r'\1# path: list[Any] = []  # 已在函数参数中定义\2',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def process_file(file_path: Path) -> bool:
    """处理单个文件"""
    try:
        filename = file_path.name
        
        # 根据文件名选择修复函数
        if filename == 'ocr_service.py':
            return fix_ocr_service(file_path)
        elif 'sms' in filename and 'stage' in str(file_path):
            return fix_sms_stages(file_path)
        elif 'task_recovery_service' in filename:
            return fix_task_recovery_service(file_path)
        elif 'clone_workflow' in filename:
            return fix_contract_workflows(file_path)
        elif filename in ['court_sms.py', 'preservation.py']:
            return fix_schemas_return_types(file_path)
        elif 'image_rotation' in filename:
            return fix_image_rotation_schema(file_path)
        elif filename == 'cache.py' and 'core' in str(file_path):
            return fix_core_cache(file_path)
        elif filename == 'file_utils.py':
            return fix_file_utils(file_path)
        elif 'anti_detection' in filename:
            return fix_anti_detection(file_path)
        elif 'captcha' in filename:
            return fix_captcha_services(file_path)
        elif 'ollama_config' in filename:
            return fix_ollama_config(file_path)
        elif filename == 'schemas.py' and 'core' in str(file_path):
            return fix_core_schemas(file_path)
        elif 'automation_factory' in filename:
            return fix_exceptions_factory(file_path)
        elif 'document_delivery' in filename and 'schema' in filename:
            return fix_document_delivery_schema(file_path)
        elif 'validation_service' in filename and 'folder_template' in str(file_path):
            return fix_folder_validation(file_path)
        
        return False
    except Exception as e:
        print(f"✗ 错误 {file_path}: {e}")
        return False


def main() -> None:
    """主函数"""
    base_dir = Path(__file__).parent.parent / "apps"
    
    fixed_count = 0
    total_count = 0
    
    for py_file in base_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        total_count += 1
        if process_file(py_file):
            print(f"✓ 修复: {py_file}")
            fixed_count += 1
    
    print(f"\n完成! 修复了 {fixed_count}/{total_count} 个文件")


if __name__ == "__main__":
    main()
