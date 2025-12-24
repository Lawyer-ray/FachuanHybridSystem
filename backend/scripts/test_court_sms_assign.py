#!/usr/bin/env python3
"""
测试法院短信指定案件功能

用法：
cd backend
source venv311/bin/activate
python scripts/test_court_sms_assign.py
"""

import os
import sys
import django

# 设置 Django 环境
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)
sys.path.insert(0, os.path.join(backend_dir, 'apiSystem'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')
django.setup()

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.cases.models import Case
from apps.automation.services.sms.court_sms_service import CourtSMSService


def test_assign_case():
    """测试指定案件功能"""
    print("🧪 测试法院短信指定案件功能")
    
    # 查找一个待手动处理的短信
    pending_sms = CourtSMS.objects.filter(
        status=CourtSMSStatus.PENDING_MANUAL
    ).first()
    
    if not pending_sms:
        print("❌ 未找到待手动处理的短信，创建测试短信...")
        pending_sms = CourtSMS.objects.create(
            content="测试短信：请及时到法院领取文书。案号：(2024)粤0604民初1234号",
            status=CourtSMSStatus.PENDING_MANUAL,
            case_numbers=["(2024)粤0604民初1234号"],
            party_names=["张三", "李四"]
        )
        print(f"✅ 创建测试短信: ID={pending_sms.id}")
    
    print(f"📱 使用短信: ID={pending_sms.id}, 状态={pending_sms.get_status_display()}")
    
    # 查找一个案件
    case = Case.objects.first()
    if not case:
        print("❌ 未找到案件，请先创建案件")
        return
    
    print(f"📁 使用案件: ID={case.id}, 名称={case.name}")
    
    # 测试指定案件
    try:
        service = CourtSMSService()
        result_sms = service.assign_case(pending_sms.id, case.id)
        
        print(f"✅ 指定案件成功!")
        print(f"   短信状态: {result_sms.get_status_display()}")
        print(f"   关联案件: {result_sms.case.name if result_sms.case else '无'}")
        
        # 检查是否触发了后续处理
        if result_sms.status == CourtSMSStatus.MATCHING:
            print("✅ 已触发后续处理流程")
        else:
            print(f"⚠️  状态异常: {result_sms.status}")
            
    except Exception as e:
        print(f"❌ 指定案件失败: {str(e)}")
        import traceback
        traceback.print_exc()


def test_search_cases():
    """测试案件搜索功能"""
    print("\n🔍 测试案件搜索功能")
    
    try:
        from apps.core.interfaces import ServiceLocator
        case_service = ServiceLocator.get_case_service()
        
        # 测试按当事人搜索
        print("测试按当事人搜索...")
        party_cases = case_service.search_cases_by_party_internal(["张三"])
        print(f"找到 {len(party_cases)} 个案件")
        
        # 测试按案号搜索
        print("测试按案号搜索...")
        number_cases = case_service.search_cases_by_case_number_internal("2024")
        print(f"找到 {len(number_cases)} 个案件")
        
        # 测试获取最近案件
        print("测试获取最近案件...")
        recent_cases = case_service.search_cases_by_party_internal([])[:5]
        print(f"找到 {len(recent_cases)} 个最近案件")
        
        for case_dto in recent_cases[:3]:
            print(f"  - ID={case_dto.id}, 名称={case_dto.name}")
            
        print("✅ 案件搜索功能正常")
        
    except Exception as e:
        print(f"❌ 案件搜索失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_assign_case()
    test_search_cases()
    print("\n🎉 测试完成")