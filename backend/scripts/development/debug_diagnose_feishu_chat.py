#!/usr/bin/env python3
"""
飞书群聊诊断脚本

用于诊断群聊创建问题，检查配置、权限和群聊状态。
"""

import json
import logging
import os
import sys

from apps.core.path import Path

project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "apiSystem"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
import django

django.setup()

from apps.automation.services.chat.feishu_provider import FeishuChatProvider
from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _mask_value(value: str | None, *, keep: int = 6) -> str:
    if not value:
        return "(空)"
    value_str = str(value)
    if len(value_str) <= keep:
        return f"<redacted len={len(value_str)}>"
    return f"<redacted len={len(value_str)} suffix={value_str[-keep:]}>"


def check_feishu_config():
    logger.info("=== 飞书配置检查 ===")

    provider = FeishuChatProvider()

    logger.info(f"提供者可用性: {provider.is_available()}")
    logger.info(f"配置信息: {list(provider.config.keys())}")

    app_id = provider.config.get("APP_ID")
    app_secret = provider.config.get("APP_SECRET")

    logger.info(f"APP_ID: {'已配置' if app_id else '未配置'}")
    logger.info(f"APP_SECRET: {'已配置' if app_secret else '未配置'}")

    return provider


def check_owner_config():
    logger.info("\n=== 群主配置检查 ===")

    manager = OwnerConfigManager()

    default_owner = manager.get_default_owner_id()
    logger.info(f"默认群主ID: {_mask_value(default_owner)}")

    config_summary = manager.get_config_summary()
    logger.info(f"配置摘要: {json.dumps(config_summary, indent=2, ensure_ascii=False)}")

    effective_owner = manager.get_effective_owner_id(None)
    logger.info(f"有效群主ID: {_mask_value(effective_owner)}")

    if effective_owner:
        is_valid = manager.validate_owner_id(effective_owner)
        logger.info(f"群主ID格式验证: {'通过' if is_valid else '失败'}")

    return manager, effective_owner


def test_access_token(provider):
    logger.info("\n=== 访问令牌测试 ===")

    try:
        token = provider._get_tenant_access_token()
        logger.info("访问令牌获取: 成功")
        logger.info(f"令牌: {_mask_value(token)}")
        return True
    except Exception as e:
        logger.info(f"访问令牌获取失败: {str(e)}")
        return False


def get_chat_info(provider, chat_id):
    logger.info(f"\n=== 群聊信息查询: {chat_id} ===")

    try:
        result = provider.get_chat_info(chat_id)

        if result.success:
            logger.info("群聊信息获取成功:")
            logger.info(json.dumps(result.raw_response, indent=2, ensure_ascii=False))

            chat_data = result.raw_response.get("data", {})
            owner_id = chat_data.get("owner_id")
            members = chat_data.get("members", [])

            logger.info(f"\n群主ID: {_mask_value(owner_id)}")
            logger.info(f"成员数量: {len(members)}")

            if members:
                logger.info("群成员:")
                for i, member in enumerate(members[:5]):
                    logger.info(f"  {i+1}. {member.get('name', '未知')} ({member.get('member_id', '未知')})")

            return chat_data
        else:
            logger.info(f"群聊信息获取失败: {result.message}")
            return None

    except Exception as e:
        logger.info(f"获取群聊信息时发生错误: {str(e)}")
        return None


def get_owner_info(provider, chat_id):
    logger.info(f"\n=== 群主信息查询: {chat_id} ===")

    try:
        owner_info = provider.get_chat_owner_info(chat_id)
        logger.info("群主信息:")
        logger.info(json.dumps(owner_info, indent=2, ensure_ascii=False))
        return owner_info
    except Exception as e:
        logger.info(f"获取群主信息时发生错误: {str(e)}")
        return None


def verify_owner_setting(provider, chat_id, expected_owner_id):
    logger.info("\n=== 群主设置验证 ===")

    if not expected_owner_id:
        logger.info("没有期望的群主ID，跳过验证")
        return False

    try:
        is_correct = provider.verify_owner_setting(chat_id, expected_owner_id)
        logger.info(f"群主设置验证结果: {'正确' if is_correct else '错误'}")
        return is_correct
    except Exception as e:
        logger.info(f"验证群主设置时发生错误: {str(e)}")
        return False


def main():
    logger.info("=== 飞书群聊诊断工具 ===")

    provider = check_feishu_config()
    _, effective_owner = check_owner_config()

    if not test_access_token(provider):
        logger.info("访问令牌获取失败，无法继续诊断")
        return

    chat_id = input("\n请输入要诊断的群聊ID (例如: oc_xxx): ").strip()

    if not chat_id:
        logger.info("未提供群聊ID，退出诊断")
        return

    chat_data = get_chat_info(provider, chat_id)
    get_owner_info(provider, chat_id)
    verify_owner_setting(provider, chat_id, effective_owner)

    logger.info("\n=== 诊断总结 ===")

    if chat_data:
        actual_owner = chat_data.get("owner_id")
        logger.info("群聊存在: 是")
        logger.info(f"实际群主: {_mask_value(actual_owner)}")
        logger.info(f"期望群主: {_mask_value(effective_owner)}")
        logger.info(f"群主匹配: {'是' if actual_owner == effective_owner else '否'}")
    else:
        logger.info("群聊不存在或无法访问")


if __name__ == "__main__":
    main()
