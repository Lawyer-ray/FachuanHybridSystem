#!/usr/bin/env python3
"""
测试保险公司列表接口，查看返回的数据格式
"""

import requests
import json

# ==================== 配置 ====================
TOKEN = "your_token_here"

# API URL - 从配置系统获取
from apps.core.config import get_config

INSURANCE_LIST_URL = get_config(
    "services.insurance.list_url",
    "https://baoquan.court.gov.cn/wsbq/ssbq/api/commoncodepz"
)

# 参数
c_pid = "category_id_here"  # 分类 ID，需要替换
fy_id = "2550"              # 法院 ID

# ==================== 测试 ====================

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

params = {
    "cPid": c_pid,
    "fyId": fy_id,
}

print("=" * 80)
print("📋 获取保险公司列表")
print("=" * 80)
print(f"URL: {INSURANCE_LIST_URL}")
print(f"参数:")
print(f"  cPid: {c_pid}")
print(f"  fyId: {fy_id}")
print(f"Token: {TOKEN[:30]}...")
print("=" * 80 + "\n")

try:
    response = requests.get(INSURANCE_LIST_URL, headers=headers, params=params, timeout=30)
    
    print("=" * 80)
    print("📥 响应")
    print("=" * 80)
    print(f"状态码: {response.status_code}")
    print(f"响应体:")
    print(response.text)
    print("=" * 80 + "\n")
    
    if response.status_code == 200:
        data = response.json()
        print("✅ 请求成功!")
        print(f"\n格式化后的数据:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        
        # 解析保险公司列表
        if isinstance(data, dict) and "data" in data:
            company_list = data.get("data", [])
        elif isinstance(data, list):
            company_list = data
        else:
            company_list = []
        
        print(f"\n📊 保险公司数量: {len(company_list)}")
        
        if company_list:
            print(f"\n🏢 保险公司列表:")
            for i, company in enumerate(company_list[:5], 1):  # 只显示前5个
                print(f"\n  {i}. {company.get('cName', 'N/A')}")
                print(f"     cId: {company.get('cId')}")
                print(f"     cCode: {company.get('cCode')}")
                print(f"     所有字段: {list(company.keys())}")
            
            if len(company_list) > 5:
                print(f"\n  ... 还有 {len(company_list) - 5} 家保险公司")
            
            # 重点：检查 cCode 的值
            print(f"\n⚠️ 重要：检查 cCode 字段")
            print(f"   第一家保险公司的 cCode: '{company_list[0].get('cCode')}'")
            print(f"   cCode 类型: {type(company_list[0].get('cCode'))}")
            print(f"   cCode 是否为数字: {str(company_list[0].get('cCode')).isdigit()}")
            
    else:
        print(f"❌ HTTP 错误: {response.status_code}")
        
except Exception as e:
    print(f"❌ 异常: {e}")
    import traceback
    traceback.print_exc()
