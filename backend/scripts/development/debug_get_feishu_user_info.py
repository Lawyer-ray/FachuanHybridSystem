#!/usr/bin/env python3
"""
获取飞书用户信息脚本

用于通过手机号或邮箱获取用户的open_id，以便配置为默认群主。
"""

import json
import logging
import os
import sys

import httpx
from apps.core.path import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "apiSystem"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
import django

django.setup()

from apps.automation.services.chat.feishu_provider import FeishuChatProvider


def get_user_by_mobile(mobile: str):
    provider = FeishuChatProvider()

    if not provider.is_available():
        logger.error("飞书提供者不可用，请检查配置")
        return None

    try:
        access_token = provider._get_tenant_access_token()

        url = f"{provider.BASE_URL}/contact/v3/users/batch_get_id"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        params = {"user_id_type": "open_id"}
        payload = {"mobiles": [mobile]}

        logger.info(f"查询手机号: {mobile}")
        with httpx.Client(timeout=30) as client:
            response = client.post(url, params=params, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        logger.info(f"API响应: {json.dumps(data, indent=2, ensure_ascii=False)}")

        if data.get("code") == 0:
            user_list = data.get("data", {}).get("user_list", [])
            if user_list:
                user = user_list[0]
                logger.info("找到用户:")
                logger.info(f"  Open ID: {user.get('user_id')}")
                logger.info(f"  手机号: {mobile}")
                return user.get("user_id")
            else:
                logger.warning(f"未找到手机号为 {mobile} 的用户")
        else:
            logger.error(f"查询失败: {data.get('msg')}")

        return None

    except Exception as e:
        logger.error(f"查询用户信息失败: {str(e)}")
        return None


def get_user_by_email(email: str):
    provider = FeishuChatProvider()

    if not provider.is_available():
        logger.error("飞书提供者不可用，请检查配置")
        return None

    try:
        access_token = provider._get_tenant_access_token()

        url = f"{provider.BASE_URL}/contact/v3/users/batch_get_id"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        params = {"user_id_type": "open_id"}
        payload = {"emails": [email]}

        logger.info(f"查询邮箱: {email}")
        with httpx.Client(timeout=30) as client:
            response = client.post(url, params=params, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        logger.info(f"API响应: {json.dumps(data, indent=2, ensure_ascii=False)}")

        if data.get("code") == 0:
            user_list = data.get("data", {}).get("user_list", [])
            if user_list:
                user = user_list[0]
                logger.info("找到用户:")
                logger.info(f"  Open ID: {user.get('user_id')}")
                logger.info(f"  邮箱: {email}")
                return user.get("user_id")
            else:
                logger.warning(f"未找到邮箱为 {email} 的用户")
        else:
            logger.error(f"查询失败: {data.get('msg')}")

        return None

    except Exception as e:
        logger.error(f"查询用户信息失败: {str(e)}")
        return None


def main():
    logger.info("=== 飞书用户信息查询工具 ===")
    logger.info("请选择查询方式:")
    logger.info("1. 通过手机号查询")
    logger.info("2. 通过邮箱查询")

    choice = input("请输入选择 (1 或 2): ").strip()

    if choice == "1":
        mobile = input("请输入手机号: ").strip()
        if mobile:
            open_id = get_user_by_mobile(mobile)
            if open_id:
                logger.info("\n✅ 查询成功！")
                logger.info("请将以下配置添加到 .env 文件:")
                logger.info(f'FEISHU_DEFAULT_OWNER_ID="{open_id}"')
        else:
            logger.warning("手机号不能为空")

    elif choice == "2":
        email = input("请输入邮箱: ").strip()
        if email:
            open_id = get_user_by_email(email)
            if open_id:
                logger.info("\n✅ 查询成功！")
                logger.info("请将以下配置添加到 .env 文件:")
                logger.info(f'FEISHU_DEFAULT_OWNER_ID="{open_id}"')
        else:
            logger.warning("邮箱不能为空")

    else:
        logger.error("无效的选择")


if __name__ == "__main__":
    main()
