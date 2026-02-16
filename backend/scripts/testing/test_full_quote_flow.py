#!/usr/bin/env python3
"""
完整的询价流程测试
1. 获取保险公司列表
2. 使用第一家保险公司进行询价
"""

import json
import os
import time

import httpx

# ==================== 配置 ====================
TOKEN = os.environ.get("COURT_BAOQUAN_TOKEN", "")
if not TOKEN:
    raise SystemExit("请设置环境变量 COURT_BAOQUAN_TOKEN 后再运行该脚本")

# 参数
c_pid = "category_id_here"  # 分类 ID，需要替换
fy_id = "2550"  # 法院 ID
preserve_amount = "3306500.22"  # 保全金额（万元）

# API URLs - 从配置系统获取
from apps.core.config import get_config

INSURANCE_LIST_URL = get_config(
    "services.insurance.list_url", "https://baoquan.court.gov.cn/wsbq/ssbq/api/commoncodepz"
)
PREMIUM_QUERY_URL = get_config(
    "services.insurance.premium_query_url", "https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium"
)


def get_insurance_companies():
    """步骤1: 获取保险公司列表"""
    print("\n" + "=" * 80)
    print("📋 步骤 1: 获取保险公司列表")
    print("=" * 80)

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    params = {
        "cPid": c_pid,
        "fyId": fy_id,
    }

    print(f"URL: {INSURANCE_LIST_URL}")
    print(f"参数: cPid={c_pid}, fyId={fy_id}")

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(INSURANCE_LIST_URL, headers=headers, params=params)

        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            # 解析保险公司列表
            if isinstance(data, dict) and "data" in data:
                company_list = data.get("data", [])
            elif isinstance(data, list):
                company_list = data
            else:
                company_list = []

            print(f"✅ 获取到 {len(company_list)} 家保险公司")

            if company_list:
                print(f"\n前3家保险公司:")
                for i, company in enumerate(company_list[:3], 1):
                    print(f"  {i}. {company.get('cName')}")
                    print(f"     cId: {company.get('cId')}")
                    print(f"     cCode: {company.get('cCode')}")

                return company_list
            else:
                print("❌ 保险公司列表为空")
                return None
        else:
            print(f"❌ HTTP 错误: {response.status_code}")
            print(f"响应: {response.text}")
            return None

    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback

        traceback.print_exc()
        return None


def query_premium(company):
    """步骤2: 查询保险公司报价"""
    print("\n" + "=" * 80)
    print(f"💰 步骤 2: 查询保险公司报价 - {company.get('cName')}")
    print("=" * 80)

    # 生成时间戳
    current_time_ms = str(int(time.time() * 1000))

    # 获取保险公司代码
    institution = str(company.get("cCode"))

    print(f"保险公司信息:")
    print(f"  名称: {company.get('cName')}")
    print(f"  cId: {company.get('cId')}")
    print(f"  cCode: {institution}")
    print(f"  cCode 类型: {type(institution)}")

    # 请求头
    headers = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Bearer": TOKEN,
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://zxfw.court.gov.cn",
        "Pragma": "no-cache",
        "Referer": "https://zxfw.court.gov.cn/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    }

    # URL 参数
    params = {
        "time": current_time_ms,
        "preserveAmount": preserve_amount,
        "institution": institution,
        "corpId": fy_id,
    }

    # 请求体
    request_body = {
        "preserveAmount": preserve_amount,
        "institution": institution,
        "corpId": fy_id,
    }

    print(f"\n请求参数:")
    print(f"  time: {current_time_ms}")
    print(f"  preserveAmount: {preserve_amount}")
    print(f"  institution: {institution}")
    print(f"  corpId: {fy_id}")

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                PREMIUM_QUERY_URL,
                headers=headers,
                params=params,
                json=request_body,
            )

        print(f"\n状态码: {response.status_code}")
        print(f"完整 URL: {response.url}")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ 询价成功!")
            print(f"响应数据:")
            print(json.dumps(data, ensure_ascii=False, indent=2))

            # 提取 data 字段中的费率信息
            rate_data = data.get("data", {})
            if rate_data:
                print(f"\n" + "=" * 60)
                print(f"💰 费率信息详情")
                print(f"=" * 60)
                print(f"  最低收费1 (minPremium):    {rate_data.get('minPremium', 'N/A')} 元")
                print(f"  最低收费2 (minAmount):     {rate_data.get('minAmount', 'N/A')} 元")
                print(f"  最低费率 (minRate):        {rate_data.get('minRate', 'N/A')}")
                print(f"  最高费率 (maxRate):        {rate_data.get('maxRate', 'N/A')}")
                print(f"  最高收费 (maxAmount):      {rate_data.get('maxAmount', 'N/A')} 元")
                print(f"  最高保全金额 (maxApplyAmount): {rate_data.get('maxApplyAmount', 'N/A')} 元")
                print(f"=" * 60)
            else:
                print(f"\n⚠️ 响应中未找到费率数据")

            return True
        else:
            print(f"❌ HTTP 错误: {response.status_code}")
            print(f"响应: {response.text}")
            return False

    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主流程"""
    print("\n🚀 开始完整询价流程测试\n")
    print(f"配置:")
    print("  Token: 已从环境变量读取")
    print(f"  分类ID (cPid): {c_pid}")
    print(f"  法院ID (fyId): {fy_id}")
    print(f"  保全金额: {preserve_amount} 万元")

    # 步骤1: 获取保险公司列表
    companies = get_insurance_companies()

    if not companies:
        print("\n❌ 无法获取保险公司列表，测试终止")
        return

    # 等待一下
    print("\n⏳ 等待 2 秒...")
    time.sleep(2)

    # 步骤2: 查询第一家保险公司报价
    success = query_premium(companies[0])

    # 总结
    print("\n" + "=" * 80)
    print("📊 测试总结")
    print("=" * 80)
    if success:
        print("✅ 完整流程测试成功!")
    else:
        print("❌ 询价失败，请检查参数")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
