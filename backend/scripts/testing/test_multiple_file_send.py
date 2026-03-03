#!/usr/bin/env python3
"""
测试多文件发送功能

验证修改后的案件群聊服务是否能正确发送所有下载的文件到群聊中。
"""

import os
import sys

import django

from apps.core.path import Path

project_root = Path(__file__).parent.parent.parent
api_system_path = project_root / "apiSystem"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(api_system_path))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from apps.automation.models import CourtSMS
from apps.cases.services.case_chat_service import CaseChatService
from apps.core.enums import ChatPlatform


def test_multiple_file_notification():
    print("=== 测试多文件发送功能 ===")

    sms_with_files = CourtSMS.objects.filter(scraper_task__isnull=False, case__isnull=False).first()

    if not sms_with_files:
        print("❌ 未找到有下载任务和案件绑定的短信记录")
        return

    print(f"📋 找到短信记录: ID={sms_with_files.id}")
    print(f"📋 绑定案件: {sms_with_files.case.name}")

    if not sms_with_files.scraper_task:
        print("❌ 短信没有关联的下载任务")
        return

    documents = sms_with_files.scraper_task.documents.filter(download_status="success")
    document_count = documents.count()

    print(f"📁 找到 {document_count} 个下载成功的文件:")

    document_paths = []
    for i, doc in enumerate(documents, 1):
        print(f"   {i}. {doc.c_wsmc} -> {doc.local_file_path}")
        if doc.local_file_path and os.path.exists(doc.local_file_path):
            document_paths.append(doc.local_file_path)
            print("      ✅ 文件存在")
        else:
            print("      ❌ 文件不存在或路径为空")

    if not document_paths:
        print("❌ 没有可用的文件路径")
        return

    print(f"\n📤 准备发送 {len(document_paths)} 个文件到群聊...")

    try:
        chat_service = CaseChatService()

        result = chat_service.send_document_notification(
            case_id=sms_with_files.case.id,
            sms_content=sms_with_files.content,
            document_paths=document_paths,
            platform=ChatPlatform.FEISHU,
            title="🧪 测试多文件发送",
        )

        if result.success:
            print("✅ 多文件发送测试成功!")
            print(f"📝 结果消息: {result.message}")
        else:
            print("❌ 多文件发送测试失败!")
            print(f"📝 错误消息: {result.message}")

    except Exception as e:
        print(f"❌ 测试过程中发生异常: {str(e)}")
        import traceback

        traceback.print_exc()


def test_backward_compatibility():
    print("\n=== 测试向后兼容性 ===")

    sms_with_file = CourtSMS.objects.filter(scraper_task__isnull=False, case__isnull=False).first()

    if not sms_with_file or not sms_with_file.scraper_task:
        print("❌ 未找到合适的测试数据")
        return

    document = sms_with_file.scraper_task.documents.filter(download_status="success").first()
    if not document or not document.local_file_path:
        print("❌ 未找到可用的文件")
        return

    print(f"📋 测试单文件发送: {document.c_wsmc}")

    try:
        chat_service = CaseChatService()

        result = chat_service.send_document_notification(
            case_id=sms_with_file.case.id,
            sms_content="测试单文件发送",
            document_paths=[document.local_file_path],
            platform=ChatPlatform.FEISHU,
            title="🧪 测试单文件发送",
        )

        if result.success:
            print("✅ 单文件发送测试成功!")
            print(f"📝 结果消息: {result.message}")
        else:
            print("❌ 单文件发送测试失败!")
            print(f"📝 错误消息: {result.message}")

    except Exception as e:
        print(f"❌ 测试过程中发生异常: {str(e)}")


def main():
    print("🚀 开始测试多文件发送功能...")
    test_multiple_file_notification()
    test_backward_compatibility()
    print("\n✨ 测试完成!")


if __name__ == "__main__":
    main()
