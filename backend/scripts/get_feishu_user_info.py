#!/usr/bin/env python3
"""
获取飞书用户信息脚本

用于通过手机号或邮箱获取用户的open_id，以便配置为默认群主。
"""

import os
import sys
import json
import requests
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / 'apiSystem'))

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')
import django
django.setup()

from apps.automation.services.chat.feishu_provider import FeishuChatProvider


def get_user_by_mobile(mobile: str):
    """通过手机号获取用户信息"""
    provider = FeishuChatProvider()
    
    if not provider.is_available():
        print("飞书提供者不可用，请检查配置")
        return None
    
    try:
        # 获取访问令牌
        access_token = provider._get_tenant_access_token()
        
        # 构建请求
        url = f"{provider.BASE_URL}/contact/v3/users/batch_get_id"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        # 查询参数
        params = {
            "user_id_type": "open_id"
        }
        
        # 请求体
        payload = {
            "mobiles": [mobile]
        }
        
        print(f"查询手机号: {mobile}")
        response = requests.post(url, params=params, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        print(f"API响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        if data.get('code') == 0:
            user_list = data.get('data', {}).get('user_list', [])
            if user_list:
                user = user_list[0]
                print(f"找到用户:")
                print(f"  Open ID: {user.get('user_id')}")
                print(f"  手机号: {mobile}")
                return user.get('user_id')
            else:
                print(f"未找到手机号为 {mobile} 的用户")
        else:
            print(f"查询失败: {data.get('msg')}")
        
        return None
        
    except Exception as e:
        print(f"查询用户信息失败: {str(e)}")
        return None


def get_user_by_email(email: str):
    """通过邮箱获取用户信息"""
    provider = FeishuChatProvider()
    
    if not provider.is_available():
        print("飞书提供者不可用，请检查配置")
        return None
    
    try:
        # 获取访问令牌
        access_token = provider._get_tenant_access_token()
        
        # 构建请求
        url = f"{provider.BASE_URL}/contact/v3/users/batch_get_id"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        # 查询参数
        params = {
            "user_id_type": "open_id"
        }
        
        # 请求体
        payload = {
            "emails": [email]
        }
        
        print(f"查询邮箱: {email}")
        response = requests.post(url, params=params, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        print(f"API响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        if data.get('code') == 0:
            user_list = data.get('data', {}).get('user_list', [])
            if user_list:
                user = user_list[0]
                print(f"找到用户:")
                print(f"  Open ID: {user.get('user_id')}")
                print(f"  邮箱: {email}")
                return user.get('user_id')
            else:
                print(f"未找到邮箱为 {email} 的用户")
        else:
            print(f"查询失败: {data.get('msg')}")
        
        return None
        
    except Exception as e:
        print(f"查询用户信息失败: {str(e)}")
        return None


def main():
    print("=== 飞书用户信息查询工具 ===")
    print("请选择查询方式:")
    print("1. 通过手机号查询")
    print("2. 通过邮箱查询")
    
    choice = input("请输入选择 (1 或 2): ").strip()
    
    if choice == "1":
        mobile = input("请输入手机号: ").strip()
        if mobile:
            open_id = get_user_by_mobile(mobile)
            if open_id:
                print(f"\n✅ 查询成功！")
                print(f"请将以下配置添加到 .env 文件:")
                print(f"FEISHU_DEFAULT_OWNER_ID=\"{open_id}\"")
        else:
            print("手机号不能为空")
    
    elif choice == "2":
        email = input("请输入邮箱: ").strip()
        if email:
            open_id = get_user_by_email(email)
            if open_id:
                print(f"\n✅ 查询成功！")
                print(f"请将以下配置添加到 .env 文件:")
                print(f"FEISHU_DEFAULT_OWNER_ID=\"{open_id}\"")
        else:
            print("邮箱不能为空")
    
    else:
        print("无效的选择")


if __name__ == "__main__":
    main()