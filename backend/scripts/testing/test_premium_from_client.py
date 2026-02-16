#!/usr/bin/env python3
"""
从 court_insurance_client.py 抽离的询价测试脚本

这个脚本完全复制了 CourtInsuranceClient.fetch_premium() 的逻辑
用于独立测试询价功能
"""

import asyncio
import json
import os
import time

import httpx

# ==================== 配置 ====================
TOKEN = os.environ.get("COURT_BAOQUAN_TOKEN", "")
if not TOKEN:
    raise SystemExit("请设置环境变量 COURT_BAOQUAN_TOKEN 后再运行该脚本")

# 测试数据
preserve_amount = "3"  # 保全金额（万元）
institution = "002"  # 保险公司代码
corp_id = "2550"  # 企业ID

# API URL - 从配置系统获取
from apps.core.config import get_config

PREMIUM_QUERY_URL = get_config(
    "services.insurance.premium_query_url", "https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium"
)


async def test_fetch_premium():
    """测试询价功能（完全复制 client 代码）"""

    # 生成毫秒级时间戳
    current_time_ms = str(int(time.time() * 1000))

    # 请求头（完全按照 client 代码）
    headers = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Bearer": TOKEN,  # 直接使用 Bearer 字段
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
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }

    # URL 查询参数
    params = {
        "time": current_time_ms,
        "preserveAmount": preserve_amount,
        "institution": institution,
        "corpId": corp_id,
    }

    # 请求体数据
    request_body = {
        "preserveAmount": preserve_amount,
        "institution": institution,
        "corpId": corp_id,
    }

    # 打印请求信息
    print("=" * 80)
    print("📤 发送询价请求")
    print("=" * 80)
    print(f"URL: {PREMIUM_QUERY_URL}")
    print(f"时间戳: {current_time_ms}")
    print(f"\nURL 参数:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    print(f"\n请求头:")
    for key, value in headers.items():
        if key == "Bearer":
            print(f"  {key}: {value[:30]}...{value[-20:]}")
        else:
            print(f"  {key}: {value}")
    print(f"\n请求体:")
    print(f"  {json.dumps(request_body, ensure_ascii=False, indent=2)}")
    print("=" * 80 + "\n")

    # 创建 httpx 客户端
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            start_time = time.time()

            # 发送 POST 请求
            response = await client.post(
                PREMIUM_QUERY_URL,
                headers=headers,
                params=params,
                json=request_body,
            )

            elapsed_time = time.time() - start_time

            # 打印响应信息
            print("=" * 80)
            print("📥 收到响应")
            print("=" * 80)
            print(f"状态码: {response.status_code}")
            print(f"响应时间: {round(elapsed_time, 3)}秒")
            print(f"完整 URL: {response.url}")
            print(f"\n响应头:")
            for key, value in response.headers.items():
                print(f"  {key}: {value}")
            print(f"\n响应体:")
            print(response.text)
            print("=" * 80 + "\n")

            # 解析响应
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ 请求成功!")
                    print(f"解析后的数据:")
                    print(json.dumps(data, ensure_ascii=False, indent=2))

                    # 提取报价
                    premium = data.get("premium") or data.get("data", {}).get("premium")
                    if premium:
                        print(f"\n💰 报价: {premium} 元")
                    else:
                        print("\n⚠️ 响应中未找到报价金额")

                except Exception as e:
                    print(f"❌ 解析响应失败: {e}")
            else:
                print(f"❌ HTTP 错误: {response.status_code}")

        except httpx.TimeoutException as e:
            print(f"❌ 请求超时: {e}")
        except httpx.HTTPError as e:
            print(f"❌ HTTP 错误: {e}")
        except Exception as e:
            print(f"❌ 未知错误: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    print("\n🚀 开始测试询价功能（从 court_insurance_client.py 抽离）\n")
    asyncio.run(test_fetch_premium())
