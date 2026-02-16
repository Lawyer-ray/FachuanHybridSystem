"""
检查测试数据

检查数据库中是否有测试所需的数据
"""

import os
import sys

import django

# 设置 Django 环境
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apiSystem"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from apps.client.models import Client
from apps.contracts.models import Contract
from apps.organization.models import Lawyer

print("=" * 80)
print("检查测试数据")
print("=" * 80)

# 检查合同
print(f"\n合同数量: {Contract.objects.count()}")
if Contract.objects.exists():
    for contract in Contract.objects.all()[:5]:
        print(f"  - ID={contract.id}, 名称={contract.name}, 代理阶段={contract.representation_stages}")

# 检查律师
print(f"\n律师数量: {Lawyer.objects.count()}")
if Lawyer.objects.exists():
    for lawyer in Lawyer.objects.all()[:5]:
        print(f"  - ID={lawyer.id}, 用户名={lawyer.username}, 真实姓名={lawyer.real_name}")

# 检查客户
print(f"\n客户数量: {Client.objects.count()}")
if Client.objects.exists():
    for client in Client.objects.all()[:5]:
        print(f"  - ID={client.id}, 姓名={client.name}")

print("\n" + "=" * 80)
