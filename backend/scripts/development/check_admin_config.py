#!/usr/bin/env python
"""
检查 Admin 配置是否正确
"""
import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')
django.setup()

from django.contrib import admin
from apps.organization.models import AccountCredential

print("=" * 60)
print("检查 Django Admin 配置")
print("=" * 60)

# 1. 检查 AccountCredential 是否已注册
print("\n1. 检查 AccountCredential 是否已注册到 Admin...")
if AccountCredential in admin.site._registry:
    print("   ✅ 已注册")
    admin_class = admin.site._registry[AccountCredential]
    print(f"   Admin 类: {admin_class.__class__.__name__}")
else:
    print("   ❌ 未注册")
    sys.exit(1)

# 2. 检查是否有 test_login_button 方法
print("\n2. 检查是否有 test_login_button 方法...")
if hasattr(admin_class, 'test_login_button'):
    print("   ✅ 存在 test_login_button 方法")
else:
    print("   ❌ 不存在 test_login_button 方法")
    print("   请确保已更新 apps/organization/admin/accountcredential_admin.py")
    sys.exit(1)

# 3. 检查是否有 test_login_view 方法
print("\n3. 检查是否有 test_login_view 方法...")
if hasattr(admin_class, 'test_login_view'):
    print("   ✅ 存在 test_login_view 方法")
else:
    print("   ❌ 不存在 test_login_view 方法")
    sys.exit(1)

# 4. 检查 list_display 是否包含 test_login_button
print("\n4. 检查 list_display 配置...")
if 'test_login_button' in admin_class.list_display:
    print("   ✅ list_display 包含 test_login_button")
else:
    print("   ❌ list_display 不包含 test_login_button")
    print(f"   当前 list_display: {admin_class.list_display}")
    sys.exit(1)

# 5. 检查自定义 URL
print("\n5. 检查自定义 URL...")
try:
    from django.urls import reverse
    # 尝试反向解析 URL
    url = reverse('admin:organization_accountcredential_test_login', args=[1])
    print(f"   ✅ 自定义 URL 已配置: {url}")
except Exception as e:
    print(f"   ❌ 自定义 URL 配置失败: {e}")
    sys.exit(1)

# 6. 检查模板文件
print("\n6. 检查模板文件...")
template_path = "apps/organization/templates/admin/organization/test_login_result.html"
if os.path.exists(template_path):
    print(f"   ✅ 模板文件存在: {template_path}")
else:
    print(f"   ❌ 模板文件不存在: {template_path}")
    sys.exit(1)

# 7. 检查依赖
print("\n7. 检查依赖...")
try:
    import ddddocr
    print("   ✅ ddddocr 已安装")
except ImportError:
    print("   ❌ ddddocr 未安装，请运行: pip install ddddocr")

try:
    from playwright.sync_api import sync_playwright
    print("   ✅ playwright 已安装")
except ImportError:
    print("   ❌ playwright 未安装，请运行: pip install playwright")

# 8. 检查 CourtZxfwService
print("\n8. 检查 CourtZxfwService...")
try:
    from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
    print("   ✅ CourtZxfwService 可导入")
except ImportError as e:
    print(f"   ❌ CourtZxfwService 导入失败: {e}")
    sys.exit(1)

# 9. 检查数据
print("\n9. 检查数据...")
credential_count = AccountCredential.objects.count()
if credential_count > 0:
    print(f"   ✅ 数据库中有 {credential_count} 条账号凭证记录")
    
    # 显示第一条记录
    first = AccountCredential.objects.first()
    print(f"   示例记录:")
    print(f"     - ID: {first.id}")
    print(f"     - 网站: {first.site_name}")
    print(f"     - 账号: {first.account}")
    print(f"     - 律师: {first.lawyer}")
else:
    print("   ⚠️  数据库中没有账号凭证记录")
    print("   请在 Admin 后台添加至少一条记录")

print("\n" + "=" * 60)
print("✅ 所有检查通过！")
print("=" * 60)
print("\n下一步:")
print("1. 重启 Django 服务（如果还没重启）")
print("2. 访问: http://127.0.0.1:8002/admin")
print("3. 导航到: 组织管理 → 账号密码")
print("4. 点击右侧的 🔐 测试登录 按钮")
print()
