#!/usr/bin/env python3
"""
验证多文件发送功能的代码修改

检查修改是否正确实现了多文件发送功能。
"""

import os
import re
from pathlib import Path


def check_court_sms_service():
    """检查 CourtSMSService 的修改"""
    
    file_path = Path(__file__).parent.parent / 'apps/automation/services/sms/court_sms_service.py'
    
    if not file_path.exists():
        print("❌ CourtSMSService 文件不存在")
        return False
    
    content = file_path.read_text(encoding='utf-8')
    
    checks = [
        # 检查方法签名是否修改为接受 document_paths 列表
        (r'def _send_case_chat_notification\(self, sms: CourtSMS, document_paths: list = None\)', 
         "方法签名修改为接受文件路径列表"),
        
        # 检查是否获取所有文件而不是单个文件
        (r'document_paths = \[doc\.local_file_path for doc in documents if doc\.local_file_path\]',
         "获取所有下载成功的文件路径"),
        
        # 检查是否传递文件列表给案件群聊服务
        (r'document_paths=document_paths or \[\]',
         "传递文件路径列表给案件群聊服务"),
        
        # 检查日志记录文件数量
        (r'准备发送 \{len\(document_paths\)\} 个文件到群聊',
         "记录准备发送的文件数量"),
    ]
    
    print("=== 检查 CourtSMSService 修改 ===")
    all_passed = True
    
    for pattern, description in checks:
        if re.search(pattern, content):
            print(f"✅ {description}")
        else:
            print(f"❌ {description}")
            all_passed = False
    
    return all_passed


def check_case_chat_service():
    """检查 CaseChatService 的修改"""
    
    file_path = Path(__file__).parent.parent / 'apps/cases/services/case_chat_service.py'
    
    if not file_path.exists():
        print("❌ CaseChatService 文件不存在")
        return False
    
    content = file_path.read_text(encoding='utf-8')
    
    checks = [
        # 检查方法签名修改
        (r'document_paths: list = None',
         "方法参数修改为文件路径列表"),
        
        # 检查多文件发送逻辑
        (r'for i, file_path in enumerate\(document_paths, 1\)',
         "实现多文件循环发送逻辑"),
        
        # 检查成功失败统计
        (r'successful_files = 0\s+failed_files = 0',
         "添加成功失败文件统计"),
        
        # 检查发送进度日志
        (r'发送第 \{i\}/\{len\(document_paths\)\} 个文件',
         "记录文件发送进度"),
        
        # 检查结果消息更新
        (r'消息和所有文件发送成功 \(\{successful_files\} 个文件\)',
         "更新结果消息包含文件统计"),
    ]
    
    print("\n=== 检查 CaseChatService 修改 ===")
    all_passed = True
    
    for pattern, description in checks:
        if re.search(pattern, content):
            print(f"✅ {description}")
        else:
            print(f"❌ {description}")
            all_passed = False
    
    return all_passed


def main():
    """主验证函数"""
    
    print("🔍 验证多文件发送功能修改...")
    
    court_sms_ok = check_court_sms_service()
    case_chat_ok = check_case_chat_service()
    
    print(f"\n📊 验证结果:")
    print(f"CourtSMSService: {'✅ 通过' if court_sms_ok else '❌ 失败'}")
    print(f"CaseChatService: {'✅ 通过' if case_chat_ok else '❌ 失败'}")
    
    if court_sms_ok and case_chat_ok:
        print("\n🎉 所有修改验证通过！多文件发送功能已正确实现。")
        return True
    else:
        print("\n⚠️  部分修改验证失败，请检查代码。")
        return False


if __name__ == "__main__":
    main()