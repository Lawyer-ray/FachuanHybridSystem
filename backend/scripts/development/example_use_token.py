#!/usr/bin/env python
"""
Token 使用示例脚本

演示如何在其他脚本中使用 TokenService 获取和使用 Token
"""
import logging
import os
import sys

import django
import httpx

from apps.core.path import Path

# 设置 Django 环境
sys.path.insert(0, str(Path(__file__).dirname().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.apiSystem.settings")
django.setup()

from apps.automation.services.scraper.core.token_service import TokenService

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _token_preview(token: str | None, *, keep: int = 6) -> str:
    if not token:
        return "(空)"
    token_str = str(token)
    if len(token_str) <= keep:
        return f"<redacted len={len(token_str)}>"
    return f"<redacted len={len(token_str)} prefix={token_str[:keep]}>"


def _safe_headers(headers: dict) -> dict:
    safe = dict(headers or {})
    auth = safe.get("Authorization")
    if isinstance(auth, str) and auth.lower().startswith("bearer "):
        safe["Authorization"] = "Bearer <redacted>"
    return safe


def example_1_get_token():
    """示例 1: 获取 Token"""
    logger.info("=" * 60)
    logger.info("示例 1: 获取 Token")
    logger.info("=" * 60)

    token_service = TokenService()

    # 获取 Token
    token = token_service.get_token("court_zxfw", "your_account")

    if token:
        logger.info("✅ Token 获取成功")
        logger.info(f"   Token: {_token_preview(token)}")
    else:
        logger.info("❌ Token 不存在或已过期")
        logger.info("   请先访问 /admin/automation/testcourt/ 进行测试登录")

    logger.info("")


def example_2_get_token_info():
    """示例 2: 获取 Token 详细信息"""
    logger.info("=" * 60)
    logger.info("示例 2: 获取 Token 详细信息")
    logger.info("=" * 60)

    token_service = TokenService()

    # 获取详细信息
    info = token_service.get_token_info("court_zxfw", "your_account")

    if info:
        logger.info("✅ Token 信息:")
        logger.info(f"   Token: {_token_preview(info.get('token'))}")
        logger.info(f"   类型: {info.get('token_type')}")
        logger.info(f"   过期时间: {info.get('expires_at')}")
        logger.info(f"   创建时间: {info.get('created_at')}")
        logger.info(f"   更新时间: {info.get('updated_at')}")
    else:
        logger.info("❌ Token 不存在或已过期")

    logger.info("")


def example_3_call_api_with_token():
    """示例 3: 使用 Token 调用 API"""
    logger.info("=" * 60)
    logger.info("示例 3: 使用 Token 调用 API")
    logger.info("=" * 60)

    token_service = TokenService()

    # 获取 Token
    token = token_service.get_token("court_zxfw", "your_account")

    if not token:
        logger.info("❌ Token 不存在或已过期，无法调用 API")
        return

    # 使用 Token 调用 API（示例）
    api_url = "https://zxfw.court.gov.cn/api/v1/user/info"  # 示例 URL

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        logger.info(f"📡 调用 API: {api_url}")
        logger.info(f"   Headers: {_safe_headers(headers)}")

        # 注意：这只是示例，实际 API 可能不同
        # response = httpx.get(api_url, headers=headers, timeout=10)
        # response.raise_for_status()
        # data = response.json()
        # print(f"✅ API 调用成功")
        # print(f"   响应: {data}")

        logger.info("   (实际调用已注释，请根据实际 API 修改)")

    except httpx.RequestError as e:
        logger.info(f"❌ API 调用失败: {e}")

    logger.info("")


def example_4_check_multiple_accounts():
    """示例 4: 检查多个账号的 Token"""
    logger.info("=" * 60)
    logger.info("示例 4: 检查多个账号的 Token")
    logger.info("=" * 60)

    token_service = TokenService()

    # 假设有多个账号
    accounts = ["account1", "account2", "account3"]

    for account in accounts:
        token = token_service.get_token("court_zxfw", account)

        if token:
            logger.info(f"✅ {account}: Token 有效")
        else:
            logger.info(f"❌ {account}: Token 不存在或已过期")

    logger.info("")


def example_5_save_token_manually():
    """示例 5: 手动保存 Token（用于测试）"""
    logger.info("=" * 60)
    logger.info("示例 5: 手动保存 Token")
    logger.info("=" * 60)

    token_service = TokenService()

    # 手动保存一个测试 Token
    test_token = "test_token_12345_abcde"

    token_service.save_token(
        site_name="court_zxfw", account="test_account", token=test_token, expires_in=3600, token_type="Bearer"  # 1 小时
    )

    logger.info("✅ Token 已保存")
    logger.info("   网站: court_zxfw")
    logger.info("   账号: test_account")
    logger.info(f"   Token: {_token_preview(test_token)}")
    logger.info("   过期时间: 3600 秒（1 小时）")

    # 验证保存
    retrieved_token = token_service.get_token("court_zxfw", "test_account")

    if retrieved_token == test_token:
        logger.info("✅ Token 验证成功")
    else:
        logger.info("❌ Token 验证失败")

    # 清理测试数据
    token_service.delete_token("court_zxfw", "test_account")
    logger.info("✅ 测试 Token 已清理")

    logger.info("")


def example_6_delete_token():
    """示例 6: 删除 Token"""
    logger.info("=" * 60)
    logger.info("示例 6: 删除 Token")
    logger.info("=" * 60)

    token_service = TokenService()

    # 先保存一个测试 Token
    token_service.save_token(site_name="court_zxfw", account="delete_test", token="token_to_delete")
    logger.info("✅ 测试 Token 已创建")

    # 确认存在
    token = token_service.get_token("court_zxfw", "delete_test")
    logger.info(f"✅ Token 存在: {token is not None}")

    # 删除
    token_service.delete_token("court_zxfw", "delete_test")
    logger.info("✅ Token 已删除")

    # 确认已删除
    token = token_service.get_token("court_zxfw", "delete_test")
    logger.info(f"✅ Token 已不存在: {token is None}")

    logger.info("")


def main():
    """主函数"""
    logger.info("\n")
    logger.info("🔑 Token Service 使用示例")
    logger.info("=" * 60)
    logger.info("")

    # 运行所有示例
    example_1_get_token()
    example_2_get_token_info()
    example_3_call_api_with_token()
    example_4_check_multiple_accounts()
    example_5_save_token_manually()
    example_6_delete_token()

    logger.info("=" * 60)
    logger.info("✅ 所有示例执行完成")
    logger.info("")
    logger.info("💡 提示:")
    logger.info("   1. 请先访问 /admin/automation/testcourt/ 进行测试登录")
    logger.info("   2. 登录成功后会自动捕获并保存 Token")
    logger.info("   3. 然后就可以在脚本中使用 TokenService 获取 Token")
    logger.info("")


if __name__ == "__main__":
    main()
