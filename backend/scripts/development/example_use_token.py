#!/usr/bin/env python
"""
Token 使用示例脚本

演示如何在其他脚本中使用 TokenService 获取和使用 Token
"""
import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.apiSystem.settings')
django.setup()

from apps.automation.services.scraper.core.token_service import TokenService
import requests


def example_1_get_token():
    """示例 1: 获取 Token"""
    print("=" * 60)
    print("示例 1: 获取 Token")
    print("=" * 60)
    
    token_service = TokenService()
    
    # 获取 Token
    token = token_service.get_token("court_zxfw", "your_account")
    
    if token:
        print(f"✅ Token 获取成功")
        print(f"   Token: {token[:50]}...")
    else:
        print("❌ Token 不存在或已过期")
        print("   请先访问 /admin/automation/testcourt/ 进行测试登录")
    
    print()


def example_2_get_token_info():
    """示例 2: 获取 Token 详细信息"""
    print("=" * 60)
    print("示例 2: 获取 Token 详细信息")
    print("=" * 60)
    
    token_service = TokenService()
    
    # 获取详细信息
    info = token_service.get_token_info("court_zxfw", "your_account")
    
    if info:
        print(f"✅ Token 信息:")
        print(f"   Token: {info['token'][:50]}...")
        print(f"   类型: {info['token_type']}")
        print(f"   过期时间: {info['expires_at']}")
        print(f"   创建时间: {info['created_at']}")
        print(f"   更新时间: {info['updated_at']}")
    else:
        print("❌ Token 不存在或已过期")
    
    print()


def example_3_call_api_with_token():
    """示例 3: 使用 Token 调用 API"""
    print("=" * 60)
    print("示例 3: 使用 Token 调用 API")
    print("=" * 60)
    
    token_service = TokenService()
    
    # 获取 Token
    token = token_service.get_token("court_zxfw", "your_account")
    
    if not token:
        print("❌ Token 不存在或已过期，无法调用 API")
        return
    
    # 使用 Token 调用 API（示例）
    api_url = "https://zxfw.court.gov.cn/api/v1/user/info"  # 示例 URL
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"📡 调用 API: {api_url}")
        print(f"   Headers: {headers}")
        
        # 注意：这只是示例，实际 API 可能不同
        # response = requests.get(api_url, headers=headers, timeout=10)
        # response.raise_for_status()
        # data = response.json()
        # print(f"✅ API 调用成功")
        # print(f"   响应: {data}")
        
        print("   (实际调用已注释，请根据实际 API 修改)")
    
    except requests.exceptions.RequestException as e:
        print(f"❌ API 调用失败: {e}")
    
    print()


def example_4_check_multiple_accounts():
    """示例 4: 检查多个账号的 Token"""
    print("=" * 60)
    print("示例 4: 检查多个账号的 Token")
    print("=" * 60)
    
    token_service = TokenService()
    
    # 假设有多个账号
    accounts = ["account1", "account2", "account3"]
    
    for account in accounts:
        token = token_service.get_token("court_zxfw", account)
        
        if token:
            print(f"✅ {account}: Token 有效")
        else:
            print(f"❌ {account}: Token 不存在或已过期")
    
    print()


def example_5_save_token_manually():
    """示例 5: 手动保存 Token（用于测试）"""
    print("=" * 60)
    print("示例 5: 手动保存 Token")
    print("=" * 60)
    
    token_service = TokenService()
    
    # 手动保存一个测试 Token
    test_token = "test_token_12345_abcde"
    
    token_service.save_token(
        site_name="court_zxfw",
        account="test_account",
        token=test_token,
        expires_in=3600,  # 1 小时
        token_type="Bearer"
    )
    
    print(f"✅ Token 已保存")
    print(f"   网站: court_zxfw")
    print(f"   账号: test_account")
    print(f"   Token: {test_token}")
    print(f"   过期时间: 3600 秒（1 小时）")
    
    # 验证保存
    retrieved_token = token_service.get_token("court_zxfw", "test_account")
    
    if retrieved_token == test_token:
        print(f"✅ Token 验证成功")
    else:
        print(f"❌ Token 验证失败")
    
    # 清理测试数据
    token_service.delete_token("court_zxfw", "test_account")
    print(f"✅ 测试 Token 已清理")
    
    print()


def example_6_delete_token():
    """示例 6: 删除 Token"""
    print("=" * 60)
    print("示例 6: 删除 Token")
    print("=" * 60)
    
    token_service = TokenService()
    
    # 先保存一个测试 Token
    token_service.save_token(
        site_name="court_zxfw",
        account="delete_test",
        token="token_to_delete"
    )
    print("✅ 测试 Token 已创建")
    
    # 确认存在
    token = token_service.get_token("court_zxfw", "delete_test")
    print(f"✅ Token 存在: {token is not None}")
    
    # 删除
    token_service.delete_token("court_zxfw", "delete_test")
    print("✅ Token 已删除")
    
    # 确认已删除
    token = token_service.get_token("court_zxfw", "delete_test")
    print(f"✅ Token 已不存在: {token is None}")
    
    print()


def main():
    """主函数"""
    print("\n")
    print("🔑 Token Service 使用示例")
    print("=" * 60)
    print()
    
    # 运行所有示例
    example_1_get_token()
    example_2_get_token_info()
    example_3_call_api_with_token()
    example_4_check_multiple_accounts()
    example_5_save_token_manually()
    example_6_delete_token()
    
    print("=" * 60)
    print("✅ 所有示例执行完成")
    print()
    print("💡 提示:")
    print("   1. 请先访问 /admin/automation/testcourt/ 进行测试登录")
    print("   2. 登录成功后会自动捕获并保存 Token")
    print("   3. 然后就可以在脚本中使用 TokenService 获取 Token")
    print()


if __name__ == "__main__":
    main()
