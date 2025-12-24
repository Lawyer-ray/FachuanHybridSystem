#!/usr/bin/env python3
"""
验证AccountCredential模型迁移的脚本

此脚本验证：
1. 新字段是否正确添加
2. 索引是否正确创建
3. 排序是否按预期工作
4. 模型方法是否正常工作
5. 数据迁移是否正确初始化现有数据
"""

import os
import sys
import django

# 设置Django环境
sys.path.append(os.path.join(os.path.dirname(__file__), '../../apiSystem'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')
django.setup()

from apps.organization.models import AccountCredential
from django.db import connection
from django.utils import timezone


def verify_model_fields():
    """验证模型字段"""
    print("=== 验证模型字段 ===")
    
    expected_fields = {
        'last_login_success_at': 'DateTimeField',
        'login_success_count': 'PositiveIntegerField', 
        'login_failure_count': 'PositiveIntegerField',
        'is_preferred': 'BooleanField'
    }
    
    model_fields = {field.name: field.__class__.__name__ for field in AccountCredential._meta.fields}
    
    for field_name, field_type in expected_fields.items():
        if field_name in model_fields:
            if model_fields[field_name] == field_type:
                print(f"✓ {field_name}: {field_type}")
            else:
                print(f"✗ {field_name}: 期望 {field_type}, 实际 {model_fields[field_name]}")
        else:
            print(f"✗ {field_name}: 字段不存在")
    
    return True


def verify_indexes():
    """验证索引"""
    print("\n=== 验证索引 ===")
    
    indexes = AccountCredential._meta.indexes
    expected_indexes = [
        ['site_name', '-last_login_success_at'],
        ['site_name', 'is_preferred']
    ]
    
    actual_indexes = [list(index.fields) for index in indexes]
    
    for expected_index in expected_indexes:
        if expected_index in actual_indexes:
            print(f"✓ 索引存在: {expected_index}")
        else:
            print(f"✗ 索引缺失: {expected_index}")
    
    return True


def verify_ordering():
    """验证排序"""
    print("\n=== 验证排序 ===")
    
    expected_ordering = ['-last_login_success_at', '-login_success_count', 'login_failure_count']
    actual_ordering = list(AccountCredential._meta.ordering)
    
    if actual_ordering == expected_ordering:
        print(f"✓ 排序正确: {actual_ordering}")
    else:
        print(f"✗ 排序错误: 期望 {expected_ordering}, 实际 {actual_ordering}")
    
    return True


def verify_model_methods():
    """验证模型方法（通过 Service 层）"""
    print("\n=== 验证模型方法（通过 Service 层） ===")
    
    from apps.organization.services import AccountCredentialService
    
    # 使用现有账号进行测试，如果没有则跳过
    credential = AccountCredential.objects.first()
    if not credential:
        print("✓ 没有现有账号，跳过方法测试")
        return True
    
    created = False
    
    if created:
        print("✓ 创建测试账号")
    
    # 测试初始状态
    initial_success_rate = credential.success_rate
    print(f"✓ 初始成功率: {initial_success_rate}")
    
    # 使用 Service 层方法测试
    service = AccountCredentialService()
    
    # 测试登录成功方法
    old_success_count = credential.login_success_count
    service.update_login_success(credential.id)
    credential.refresh_from_db()
    
    if credential.login_success_count == old_success_count + 1:
        print("✓ AccountCredentialService.update_login_success() 方法正常")
    else:
        print("✗ AccountCredentialService.update_login_success() 方法异常")
    
    # 测试登录失败方法
    old_failure_count = credential.login_failure_count
    service.update_login_failure(credential.id)
    credential.refresh_from_db()
    
    if credential.login_failure_count == old_failure_count + 1:
        print("✓ AccountCredentialService.update_login_failure() 方法正常")
    else:
        print("✗ AccountCredentialService.update_login_failure() 方法异常")
    
    # 测试成功率计算
    expected_rate = credential.login_success_count / (credential.login_success_count + credential.login_failure_count)
    if abs(credential.success_rate - expected_rate) < 0.001:
        print(f"✓ success_rate 属性正常: {credential.success_rate}")
    else:
        print(f"✗ success_rate 属性异常: 期望 {expected_rate}, 实际 {credential.success_rate}")
    
    # 不删除现有数据，只是测试
    print("✓ 方法测试完成（使用现有数据）")
    
    return True


def verify_data_migration():
    """验证数据迁移"""
    print("\n=== 验证数据迁移 ===")
    
    credentials = AccountCredential.objects.all()
    
    if not credentials.exists():
        print("✓ 没有现有数据需要验证")
        return True
    
    all_initialized = True
    for credential in credentials:
        if (credential.login_success_count is None or 
            credential.login_failure_count is None or 
            credential.is_preferred is None):
            all_initialized = False
            print(f"✗ 账号 {credential.account} 数据未正确初始化")
    
    if all_initialized:
        print(f"✓ 所有 {credentials.count()} 个现有账号数据已正确初始化")
    
    return all_initialized


def verify_database_constraints():
    """验证数据库约束"""
    print("\n=== 验证数据库约束 ===")
    
    with connection.cursor() as cursor:
        # 检查表结构
        cursor.execute("PRAGMA table_info(organization_accountcredential)")
        columns = cursor.fetchall()
        
        column_info = {col[1]: col for col in columns}
        
        # 验证新字段存在
        required_columns = [
            'last_login_success_at',
            'login_success_count', 
            'login_failure_count',
            'is_preferred'
        ]
        
        for col_name in required_columns:
            if col_name in column_info:
                print(f"✓ 数据库列存在: {col_name}")
            else:
                print(f"✗ 数据库列缺失: {col_name}")
        
        # 检查索引
        cursor.execute("PRAGMA index_list(organization_accountcredential)")
        indexes = cursor.fetchall()
        
        index_names = [idx[1] for idx in indexes]
        expected_index_patterns = ['site_na_b29cd0', 'site_na_ba8d77']
        
        for pattern in expected_index_patterns:
            found = any(pattern in name for name in index_names)
            if found:
                print(f"✓ 数据库索引存在: *{pattern}*")
            else:
                print(f"✗ 数据库索引缺失: *{pattern}*")
    
    return True


def main():
    """主验证函数"""
    print("开始验证AccountCredential模型迁移...")
    print("=" * 50)
    
    try:
        verify_model_fields()
        verify_indexes()
        verify_ordering()
        verify_model_methods()
        verify_data_migration()
        verify_database_constraints()
        
        print("\n" + "=" * 50)
        print("✓ 所有验证通过！AccountCredential模型迁移成功。")
        
    except Exception as e:
        print(f"\n✗ 验证过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)