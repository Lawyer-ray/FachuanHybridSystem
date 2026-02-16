"""
准备测试数据

为阶段验证测试准备必要的测试数据
"""
import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apiSystem'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')
django.setup()

from apps.contracts.models import Contract
from apps.organization.models import Lawyer
from apps.cases.models import CaseType

print("="*80)
print("准备测试数据")
print("="*80)

# 获取第一个律师
lawyer = Lawyer.objects.first()
if not lawyer:
    print("错误: 没有找到律师")
    sys.exit(1)

print(f"\n使用律师: ID={lawyer.id}, 用户名={lawyer.username}")

# 创建或更新测试合同
contract, created = Contract.objects.get_or_create(
    name="测试合同-阶段验证",
    defaults={
        'case_type': CaseType.CIVIL,
        'assigned_lawyer': lawyer,
        'representation_stages': ['first_trial'],  # 只包含一审
    }
)

if not created:
    # 更新现有合同
    contract.case_type = CaseType.CIVIL
    contract.representation_stages = ['first_trial']
    contract.save()
    print(f"\n更新现有合同: ID={contract.id}")
else:
    print(f"\n创建新合同: ID={contract.id}")

print(f"  - 名称: {contract.name}")
print(f"  - 案件类型: {contract.case_type}")
print(f"  - 代理阶段: {contract.representation_stages}")

print("\n" + "="*80)
print("测试数据准备完成")
print(f"请在测试中使用合同 ID: {contract.id}")
print("="*80)
