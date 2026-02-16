#!/usr/bin/env python
"""
验证合同律师指派迁移结果

检查项：
1. 所有有 assigned_lawyer 的合同都有对应的 ContractAssignment
2. 这些 ContractAssignment 的 is_primary=True 和 order=0
3. 没有重复的 ContractAssignment 记录
"""
import os
import sys

import django

# 设置 Django 环境
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apiSystem"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from apps.contracts.models import Contract, ContractAssignment


def verify_migration():
    """验证数据迁移结果"""
    print("=" * 60)
    print("合同律师指派迁移验证")
    print("=" * 60)

    # 统计信息
    total_contracts = Contract.objects.count()
    contracts_with_lawyer = Contract.objects.filter(assigned_lawyer__isnull=False).count()
    total_assignments = ContractAssignment.objects.count()
    primary_assignments = ContractAssignment.objects.filter(is_primary=True).count()

    print(f"\n📊 统计信息:")
    print(f"  - 总合同数: {total_contracts}")
    print(f"  - 有 assigned_lawyer 的合同数: {contracts_with_lawyer}")
    print(f"  - 总 ContractAssignment 记录数: {total_assignments}")
    print(f"  - 主办律师指派数: {primary_assignments}")

    # 检查 1: 所有有 assigned_lawyer 的合同都有对应的 ContractAssignment
    print(f"\n✅ 检查 1: 验证 assigned_lawyer 同步到 ContractAssignment")

    contracts_with_assigned = Contract.objects.filter(assigned_lawyer__isnull=False)
    missing_assignments = []

    for contract in contracts_with_assigned:
        assignment = ContractAssignment.objects.filter(contract=contract, lawyer=contract.assigned_lawyer).first()

        if not assignment:
            missing_assignments.append(contract.id)

    if missing_assignments:
        print(f"  ❌ 发现 {len(missing_assignments)} 个合同缺少对应的 ContractAssignment:")
        for contract_id in missing_assignments[:10]:  # 只显示前 10 个
            print(f"     - Contract ID: {contract_id}")
        if len(missing_assignments) > 10:
            print(f"     ... 还有 {len(missing_assignments) - 10} 个")
    else:
        print(f"  ✅ 所有有 assigned_lawyer 的合同都有对应的 ContractAssignment")

    # 检查 2: 验证 is_primary=True 和 order=0
    print(f"\n✅ 检查 2: 验证 is_primary 和 order 字段")

    incorrect_assignments = []

    for contract in contracts_with_assigned:
        assignment = ContractAssignment.objects.filter(contract=contract, lawyer=contract.assigned_lawyer).first()

        if assignment:
            if not assignment.is_primary or assignment.order != 0:
                incorrect_assignments.append(
                    {
                        "contract_id": contract.id,
                        "assignment_id": assignment.id,
                        "is_primary": assignment.is_primary,
                        "order": assignment.order,
                    }
                )

    if incorrect_assignments:
        print(f"  ❌ 发现 {len(incorrect_assignments)} 个 ContractAssignment 字段不正确:")
        for item in incorrect_assignments[:10]:
            print(
                f"     - Contract ID: {item['contract_id']}, "
                f"Assignment ID: {item['assignment_id']}, "
                f"is_primary: {item['is_primary']}, "
                f"order: {item['order']}"
            )
        if len(incorrect_assignments) > 10:
            print(f"     ... 还有 {len(incorrect_assignments) - 10} 个")
    else:
        print(f"  ✅ 所有从 assigned_lawyer 同步的 ContractAssignment 都有正确的 is_primary=True 和 order=0")

    # 检查 3: 验证没有重复的 ContractAssignment
    print(f"\n✅ 检查 3: 验证没有重复的 ContractAssignment")

    from django.db.models import Count

    duplicates = ContractAssignment.objects.values("contract", "lawyer").annotate(count=Count("id")).filter(count__gt=1)

    if duplicates.exists():
        print(f"  ❌ 发现 {duplicates.count()} 组重复的 ContractAssignment:")
        for dup in list(duplicates)[:10]:
            print(f"     - Contract ID: {dup['contract']}, Lawyer ID: {dup['lawyer']}, 数量: {dup['count']}")
        if duplicates.count() > 10:
            print(f"     ... 还有 {duplicates.count() - 10} 组")
    else:
        print(f"  ✅ 没有重复的 ContractAssignment 记录")

    # 检查 4: 验证每个合同最多只有一个主办律师
    print(f"\n✅ 检查 4: 验证每个合同最多只有一个主办律师")

    contracts_with_multiple_primary = Contract.objects.annotate(
        primary_count=Count("assignments", filter=models.Q(assignments__is_primary=True))
    ).filter(primary_count__gt=1)

    if contracts_with_multiple_primary.exists():
        print(f"  ❌ 发现 {contracts_with_multiple_primary.count()} 个合同有多个主办律师:")
        for contract in list(contracts_with_multiple_primary)[:10]:
            primary_lawyers = contract.assignments.filter(is_primary=True)
            print(f"     - Contract ID: {contract.id}, 主办律师数: {primary_lawyers.count()}")
        if contracts_with_multiple_primary.count() > 10:
            print(f"     ... 还有 {contracts_with_multiple_primary.count() - 10} 个")
    else:
        print(f"  ✅ 每个合同最多只有一个主办律师")

    # 总结
    print(f"\n" + "=" * 60)
    all_checks_passed = (
        not missing_assignments
        and not incorrect_assignments
        and not duplicates.exists()
        and not contracts_with_multiple_primary.exists()
    )

    if all_checks_passed:
        print("✅ 所有检查通过！数据迁移成功！")
        return 0
    else:
        print("❌ 部分检查未通过，请查看上述详细信息")
        return 1


if __name__ == "__main__":
    from django.db import models

    exit_code = verify_migration()
    sys.exit(exit_code)
