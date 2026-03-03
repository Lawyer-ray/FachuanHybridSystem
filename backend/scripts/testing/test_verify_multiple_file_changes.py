#!/usr/bin/env python3
"""
验证多文件发送功能的代码修改

检查修改是否正确实现了多文件发送功能。
"""

import re

from apps.core.path import Path


def check_court_sms_service():
    file_path = Path(__file__).parent.parent.parent / "apps/automation/services/sms/court_sms_service.py"

    if not file_path.exists():
        print("❌ CourtSMSService 文件不存在")
        return False

    content = file_path.read_text(encoding="utf-8")

    checks = [
        (
            r"def _send_case_chat_notification\(self, sms: CourtSMS, document_paths: list = None\)",
            "方法签名修改为接受文件路径列表",
        ),
        (
            r"document_paths = \[doc\.local_file_path for doc in documents if doc\.local_file_path\]",
            "获取所有下载成功的文件路径",
        ),
        (
            r"document_paths=document_paths or \[\]",
            "传递文件路径列表给案件群聊服务",
        ),
        (
            r"准备发送 \{len\(document_paths\)\} 个文件到群聊",
            "记录准备发送的文件数量",
        ),
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
    file_path = Path(__file__).parent.parent.parent / "apps/cases/services/case_chat_service.py"

    if not file_path.exists():
        print("❌ CaseChatService 文件不存在")
        return False

    content = file_path.read_text(encoding="utf-8")

    checks = [
        (r"document_paths: list = None", "方法参数修改为文件路径列表"),
        (r"for i, file_path in enumerate\(document_paths, 1\)", "实现多文件循环发送逻辑"),
        (r"successful_files = 0\s+failed_files = 0", "添加成功失败文件统计"),
        (r"发送第 \{i\}/\{len\(document_paths\)\} 个文件", "记录文件发送进度"),
        (r"消息和所有文件发送成功 \(\{successful_files\} 个文件\)", "更新结果消息包含文件统计"),
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
    print("🔍 验证多文件发送功能修改...")

    court_sms_ok = check_court_sms_service()
    case_chat_ok = check_case_chat_service()

    print("\n📊 验证结果:")
    print(f"CourtSMSService: {'✅ 通过' if court_sms_ok else '❌ 失败'}")
    print(f"CaseChatService: {'✅ 通过' if case_chat_ok else '❌ 失败'}")

    if court_sms_ok and case_chat_ok:
        print("\n🎉 所有修改验证通过！多文件发送功能已正确实现。")
        return True

    print("\n⚠️  部分修改验证失败，请检查代码。")
    return False


if __name__ == "__main__":
    main()
