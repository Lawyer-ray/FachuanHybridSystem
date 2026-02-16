#!/usr/bin/env python
"""
Token 捕获调试脚本

用于诊断为什么 Token 没有被捕获和保存
"""
import logging
import os
import re
import sys

import django

# 设置 Django 环境
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.apiSystem.settings")
django.setup()

from django.core.cache import cache

from apps.automation.models import CourtToken
from apps.automation.services.scraper.core.token_service import TokenService

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_SENSITIVE_VALUE_RE = re.compile(r"(bearer\s+)([A-Za-z0-9_\-\.=]{12,})", re.IGNORECASE)
_TOKEN_KV_RE = re.compile(
    r'("?(token|authorization|api[_-]?key|secret|password)"?\s*[:=]\s*)("?)([^",\s]{12,})\3', re.IGNORECASE
)


def _redact_text(text: str) -> str:
    if not text:
        return text
    text = _SENSITIVE_VALUE_RE.sub(r"\1<redacted>", text)
    return _TOKEN_KV_RE.sub(r"\1<redacted>", text)


def _token_preview(token: str | None, *, keep: int = 6) -> str:
    if not token:
        return "(空)"
    token_str = str(token)
    if len(token_str) <= keep:
        return f"<redacted len={len(token_str)}>"
    return f"<redacted len={len(token_str)} prefix={token_str[:keep]}>"


def check_cache_connection():
    """检查缓存连接"""
    logger.info("=" * 60)
    logger.info("1. 检查缓存连接")
    logger.info("=" * 60)

    try:
        # 测试缓存连接
        cache.set("test_key", "test_value", timeout=10)
        value = cache.get("test_key")

        if value == "test_value":
            logger.info("✅ 缓存连接正常")
            cache.delete("test_key")
            return True
        else:
            logger.info("❌ 缓存连接异常：无法读取写入的值")
            return False
    except Exception as e:
        logger.info(f"❌ 缓存连接失败: {e}")
        return False


def check_database():
    """检查数据库"""
    logger.info("\n" + "=" * 60)
    logger.info("2. 检查数据库")
    logger.info("=" * 60)

    try:
        # 检查 CourtToken 表是否存在
        count = CourtToken.objects.count()
        logger.info("✅ 数据库连接正常")
        logger.info(f"   CourtToken 表中有 {count} 条记录")
        return True
    except Exception as e:
        logger.info(f"❌ 数据库连接失败: {e}")
        logger.info("   请确保已执行数据库迁移: make migrate-token")
        return False


def list_existing_tokens():
    """列出现有的 Token"""
    logger.info("\n" + "=" * 60)
    logger.info("3. 现有 Token 列表")
    logger.info("=" * 60)

    try:
        tokens = CourtToken.objects.all().order_by("-created_at")

        if tokens:
            logger.info(f"找到 {tokens.count()} 个 Token:\n")
            for token in tokens:
                status = "✅ 有效" if not token.is_expired() else "❌ 已过期"
                logger.info(f"  {status} | {token.site_name} | {token.account}")
                logger.info(f"     Token: {_token_preview(token.token)}")
                logger.info(f"     过期时间: {token.expires_at}")
                logger.info(f"     创建时间: {token.created_at}")
                logger.info("")
        else:
            logger.info("⚠️ 数据库中没有 Token")
            logger.info("   请先通过测试登录创建 Token")
    except Exception as e:
        logger.info(f"❌ 查询 Token 失败: {e}")


def test_token_service():
    """测试 TokenService"""
    logger.info("\n" + "=" * 60)
    logger.info("4. 测试 TokenService")
    logger.info("=" * 60)

    token_service = TokenService()
    test_site = "test_site"
    test_account = "test_account"
    test_token = "test_token_12345"

    try:
        # 测试保存
        logger.info("📝 测试保存 Token...")
        token_service.save_token(site_name=test_site, account=test_account, token=test_token, expires_in=300)  # 5 分钟
        logger.info("✅ Token 保存成功")

        # 测试获取
        logger.info("\n📖 测试获取 Token...")
        retrieved_token = token_service.get_token(test_site, test_account)

        if retrieved_token == test_token:
            logger.info("✅ Token 获取成功")
            logger.info(f"   获取的 Token: {_token_preview(retrieved_token)}")
        else:
            logger.info("❌ Token 获取失败")
            logger.info(f"   期望: {_token_preview(test_token)}")
            logger.info(f"   实际: {_token_preview(retrieved_token)}")

        # 测试删除
        logger.info("\n🗑️  测试删除 Token...")
        token_service.delete_token(test_site, test_account)

        # 确认已删除
        deleted_token = token_service.get_token(test_site, test_account)
        if deleted_token is None:
            logger.info("✅ Token 删除成功")
        else:
            logger.info("❌ Token 删除失败")

        return True

    except Exception as e:
        logger.info(f"❌ TokenService 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def check_logs():
    """检查日志文件"""
    logger.info("\n" + "=" * 60)
    logger.info("5. 检查日志文件")
    logger.info("=" * 60)

    log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    api_log = os.path.join(log_dir, "api.log")

    if os.path.exists(api_log):
        logger.info(f"✅ 日志文件存在: {api_log}")
        logger.info("\n最近的 Token 相关日志:")
        logger.info("-" * 60)

        try:
            with open(api_log, "r", encoding="utf-8") as f:
                lines = f.readlines()
                token_lines = [line for line in lines[-200:] if "token" in line.lower() or "Token" in line]

                if token_lines:
                    for line in token_lines[-10:]:  # 只显示最后 10 条
                        logger.info(_redact_text(line.strip()))
                else:
                    logger.info("⚠️ 没有找到 Token 相关的日志")
        except Exception as e:
            logger.info(f"❌ 读取日志失败: {e}")
    else:
        logger.info(f"⚠️ 日志文件不存在: {api_log}")


def print_troubleshooting_tips():
    """打印故障排查建议"""
    logger.info("\n" + "=" * 60)
    logger.info("6. 故障排查建议")
    logger.info("=" * 60)

    logger.info(
        """
如果 Token 没有被捕获，请检查以下几点：

1. 确认数据库迁移已执行
   cd backend && make migrate-token

2. 查看登录时的日志
   tail -f backend/logs/api.log
   # 查找包含 "Token" 或 "拦截" 的日志

3. 确认登录接口返回了 Token
   - 查看日志中的 "📄 响应内容" 部分
   - 确认响应中包含 token 字段

4. 检查网络拦截器是否触发
   - 查看日志中的 "🔍 拦截到请求" 部分
   - 应该能看到登录接口的请求

5. 手动测试 TokenService
   python scripts/debug_token_capture.py

6. 在 Django Shell 中测试
   python apiSystem/manage.py shell
   >>> from apps.automation.services.scraper.core.token_service import TokenService
   >>> ts = TokenService()
   >>> ts.save_token("test", "test", "test_token")
   >>> ts.get_token("test", "test")

7. 查看 Admin 后台
   http://localhost:8000/admin/automation/courttoken/
   确认 Token 是否已保存

如果问题仍然存在，请提供：
- 登录时的完整日志
- 登录接口的响应格式
- 是否看到 "拦截到请求" 的日志
"""
    )


def main():
    """主函数"""
    logger.info("\n")
    logger.info("🔍 Token 捕获调试工具")
    logger.info("=" * 60)
    logger.info("")

    # 执行所有检查
    cache_ok = check_cache_connection()
    db_ok = check_database()

    if db_ok:
        list_existing_tokens()

    if cache_ok and db_ok:
        test_token_service()

    check_logs()
    print_troubleshooting_tips()

    logger.info("\n" + "=" * 60)
    logger.info("✅ 调试完成")
    logger.info("=" * 60)
    logger.info("")


if __name__ == "__main__":
    main()
