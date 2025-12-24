#!/usr/bin/env python
"""
Token 捕获调试脚本

用于诊断为什么 Token 没有被捕获和保存
"""
import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.apiSystem.settings')
django.setup()

from apps.automation.services.scraper.core.token_service import TokenService
from apps.automation.models import CourtToken
from django.core.cache import cache


def check_redis_connection():
    """检查 Redis 连接"""
    print("=" * 60)
    print("1. 检查 Redis 连接")
    print("=" * 60)
    
    try:
        # 测试 Redis 连接
        cache.set("test_key", "test_value", timeout=10)
        value = cache.get("test_key")
        
        if value == "test_value":
            print("✅ Redis 连接正常")
            cache.delete("test_key")
            return True
        else:
            print("❌ Redis 连接异常：无法读取写入的值")
            return False
    except Exception as e:
        print(f"❌ Redis 连接失败: {e}")
        return False


def check_database():
    """检查数据库"""
    print("\n" + "=" * 60)
    print("2. 检查数据库")
    print("=" * 60)
    
    try:
        # 检查 CourtToken 表是否存在
        count = CourtToken.objects.count()
        print(f"✅ 数据库连接正常")
        print(f"   CourtToken 表中有 {count} 条记录")
        return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        print("   请确保已执行数据库迁移: make migrate-token")
        return False


def list_existing_tokens():
    """列出现有的 Token"""
    print("\n" + "=" * 60)
    print("3. 现有 Token 列表")
    print("=" * 60)
    
    try:
        tokens = CourtToken.objects.all().order_by('-created_at')
        
        if tokens:
            print(f"找到 {tokens.count()} 个 Token:\n")
            for token in tokens:
                status = "✅ 有效" if not token.is_expired() else "❌ 已过期"
                print(f"  {status} | {token.site_name} | {token.account}")
                print(f"     Token: {token.token[:50]}...")
                print(f"     过期时间: {token.expires_at}")
                print(f"     创建时间: {token.created_at}")
                print()
        else:
            print("⚠️ 数据库中没有 Token")
            print("   请先通过测试登录创建 Token")
    except Exception as e:
        print(f"❌ 查询 Token 失败: {e}")


def test_token_service():
    """测试 TokenService"""
    print("\n" + "=" * 60)
    print("4. 测试 TokenService")
    print("=" * 60)
    
    token_service = TokenService()
    test_site = "test_site"
    test_account = "test_account"
    test_token = "test_token_12345"
    
    try:
        # 测试保存
        print("📝 测试保存 Token...")
        token_service.save_token(
            site_name=test_site,
            account=test_account,
            token=test_token,
            expires_in=300  # 5 分钟
        )
        print("✅ Token 保存成功")
        
        # 测试获取
        print("\n📖 测试获取 Token...")
        retrieved_token = token_service.get_token(test_site, test_account)
        
        if retrieved_token == test_token:
            print("✅ Token 获取成功")
            print(f"   获取的 Token: {retrieved_token}")
        else:
            print("❌ Token 获取失败")
            print(f"   期望: {test_token}")
            print(f"   实际: {retrieved_token}")
        
        # 测试删除
        print("\n🗑️  测试删除 Token...")
        token_service.delete_token(test_site, test_account)
        
        # 确认已删除
        deleted_token = token_service.get_token(test_site, test_account)
        if deleted_token is None:
            print("✅ Token 删除成功")
        else:
            print("❌ Token 删除失败")
        
        return True
    
    except Exception as e:
        print(f"❌ TokenService 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_logs():
    """检查日志文件"""
    print("\n" + "=" * 60)
    print("5. 检查日志文件")
    print("=" * 60)
    
    log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
    api_log = os.path.join(log_dir, 'api.log')
    
    if os.path.exists(api_log):
        print(f"✅ 日志文件存在: {api_log}")
        print("\n最近的 Token 相关日志:")
        print("-" * 60)
        
        try:
            with open(api_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                token_lines = [line for line in lines[-200:] if 'token' in line.lower() or 'Token' in line]
                
                if token_lines:
                    for line in token_lines[-10:]:  # 只显示最后 10 条
                        print(line.strip())
                else:
                    print("⚠️ 没有找到 Token 相关的日志")
        except Exception as e:
            print(f"❌ 读取日志失败: {e}")
    else:
        print(f"⚠️ 日志文件不存在: {api_log}")


def print_troubleshooting_tips():
    """打印故障排查建议"""
    print("\n" + "=" * 60)
    print("6. 故障排查建议")
    print("=" * 60)
    
    print("""
如果 Token 没有被捕获，请检查以下几点：

1. 确认数据库迁移已执行
   cd backend && make migrate-token

2. 确认 Redis 服务正常运行
   redis-cli ping
   # 应该返回 PONG

3. 查看登录时的日志
   tail -f backend/logs/api.log
   # 查找包含 "Token" 或 "拦截" 的日志

4. 确认登录接口返回了 Token
   - 查看日志中的 "📄 响应内容" 部分
   - 确认响应中包含 token 字段

5. 检查网络拦截器是否触发
   - 查看日志中的 "🔍 拦截到请求" 部分
   - 应该能看到登录接口的请求

6. 手动测试 TokenService
   python scripts/debug_token_capture.py

7. 在 Django Shell 中测试
   python apiSystem/manage.py shell
   >>> from apps.automation.services.scraper.core.token_service import TokenService
   >>> ts = TokenService()
   >>> ts.save_token("test", "test", "test_token")
   >>> ts.get_token("test", "test")

8. 查看 Admin 后台
   http://localhost:8000/admin/automation/courttoken/
   确认 Token 是否已保存

如果问题仍然存在，请提供：
- 登录时的完整日志
- 登录接口的响应格式
- 是否看到 "拦截到请求" 的日志
""")


def main():
    """主函数"""
    print("\n")
    print("🔍 Token 捕获调试工具")
    print("=" * 60)
    print()
    
    # 执行所有检查
    redis_ok = check_redis_connection()
    db_ok = check_database()
    
    if db_ok:
        list_existing_tokens()
    
    if redis_ok and db_ok:
        test_token_service()
    
    check_logs()
    print_troubleshooting_tips()
    
    print("\n" + "=" * 60)
    print("✅ 调试完成")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
