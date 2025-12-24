# 合同律师指派重构方案

## 背景

当前合同有两种律师指派方式：
1. `assigned_lawyer` - 单个主办律师（必填）
2. `ContractAssignment` - 多个协办律师（可选）

这种设计存在冗余，建议简化为只使用 `ContractAssignment`。

## 重构目标

统一使用 `ContractAssignment` 管理所有律师指派，通过 `is_primary` 字段标识主办律师。

## 数据模型变更

### 修改前
```python
class Contract(models.Model):
    assigned_lawyer = ForeignKey(Lawyer, ...)  # 必填，主办律师
    
class ContractAssignment(models.Model):
    contract = ForeignKey(Contract, ...)
    lawyer = ForeignKey(Lawyer, ...)
    # 协办律师
```

### 修改后
```python
class Contract(models.Model):
    assigned_lawyer = ForeignKey(Lawyer, null=True, blank=True, ...)  # 改为可选，保留用于兼容
    
class ContractAssignment(models.Model):
    contract = ForeignKey(Contract, ...)
    lawyer = ForeignKey(Lawyer, ...)
    is_primary = BooleanField(default=False)  # 新增：标识主办律师
    order = IntegerField(default=0)  # 新增：排序
```

## 实施步骤

### 阶段 1：数据库迁移（保持兼容）

1. 修改 `Contract.assigned_lawyer` 为可选字段
2. 在 `ContractAssignment` 添加 `is_primary` 和 `order` 字段
3. 数据迁移：将现有 `assigned_lawyer` 同步到 `ContractAssignment`

### 阶段 2：代码更新

1. 更新 Service 层逻辑
2. 更新 API Schema
3. 更新查询优化
4. 更新权限检查

### 阶段 3：清理（可选）

1. 废弃 `assigned_lawyer` 字段
2. 移除相关代码

## 详细实施

### 1. 模型修改

```python
# apps/contracts/models.py

class Contract(models.Model):
    # 改为可选，保留用于向后兼容
    assigned_lawyer = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.PROTECT,
        related_name="contracts",
        verbose_name=_("指派律师（已废弃）"),
        null=True,
        blank=True,
        help_text="此字段已废弃，请使用 ContractAssignment"
    )
    
    @property
    def primary_lawyer(self):
        """获取主办律师"""
        assignment = self.assignments.filter(is_primary=True).first()
        return assignment.lawyer if assignment else self.assigned_lawyer
    
    @property
    def all_lawyers(self):
        """获取所有律师（包括主办和协办）"""
        return [a.lawyer for a in self.assignments.order_by('-is_primary', 'order')]


class ContractAssignment(models.Model):
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("合同")
    )
    lawyer = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        related_name="contract_assignments",
        verbose_name=_("律师")
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name=_("是否主办律师")
    )
    order = models.IntegerField(
        default=0,
        verbose_name=_("排序")
    )
    
    class Meta:
        verbose_name = _("合同指派")
        verbose_name_plural = _("合同指派")
        unique_together = ("contract", "lawyer")
        ordering = ['-is_primary', 'order']
```

### 2. 数据迁移

```python
# 迁移文件：0014_refactor_lawyer_assignment.py

from django.db import migrations, models

def migrate_assigned_lawyer_to_assignment(apps, schema_editor):
    """将 assigned_lawyer 迁移到 ContractAssignment"""
    Contract = apps.get_model('contracts', 'Contract')
    ContractAssignment = apps.get_model('contracts', 'ContractAssignment')
    
    for contract in Contract.objects.filter(assigned_lawyer__isnull=False):
        # 创建主办律师的 Assignment
        ContractAssignment.objects.get_or_create(
            contract=contract,
            lawyer=contract.assigned_lawyer,
            defaults={
                'is_primary': True,
                'order': 0
            }
        )

class Migration(migrations.Migration):
    dependencies = [
        ('contracts', '0013_supplementaryagreement_supplementaryagreementparty_and_more'),
    ]
    
    operations = [
        # 1. 添加新字段
        migrations.AddField(
            model_name='contractassignment',
            name='is_primary',
            field=models.BooleanField(default=False, verbose_name='是否主办律师'),
        ),
        migrations.AddField(
            model_name='contractassignment',
            name='order',
            field=models.IntegerField(default=0, verbose_name='排序'),
        ),
        
        # 2. 修改 assigned_lawyer 为可选
        migrations.AlterField(
            model_name='contract',
            name='assigned_lawyer',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='contracts',
                to='organization.lawyer',
                verbose_name='指派律师（已废弃）'
            ),
        ),
        
        # 3. 数据迁移
        migrations.RunPython(
            migrate_assigned_lawyer_to_assignment,
            reverse_code=migrations.RunPython.noop
        ),
        
        # 4. 添加约束：每个合同最多一个主办律师
        migrations.AddConstraint(
            model_name='contractassignment',
            constraint=models.CheckConstraint(
                check=models.Q(is_primary=False) | models.Q(is_primary=True),
                name='contract_one_primary_lawyer'
            ),
        ),
    ]
```

### 3. Schema 更新

```python
# apps/contracts/schemas.py

class ContractIn(ModelSchema):
    # 移除 assigned_lawyer_id
    # assigned_lawyer_id: int  # 删除
    
    # 改用 lawyer_ids，第一个为主办律师
    lawyer_ids: List[int]  # 必填，至少一个
    
    @model_validator(mode="after")
    def validate_lawyers(self):
        lawyer_ids = getattr(self, "lawyer_ids", None)
        if not lawyer_ids or len(lawyer_ids) == 0:
            raise ValueError("至少需要指派一个律师")
        return self


class ContractAssignmentOut(ModelSchema):
    lawyer_detail: LawyerOut
    
    class Meta:
        model = ContractAssignment
        fields = ["id", "lawyer", "is_primary", "order"]
    
    @staticmethod
    def resolve_lawyer_detail(obj):
        return obj.lawyer


class ContractOut(ModelSchema):
    # 移除 assigned_lawyer_detail
    # assigned_lawyer_detail: LawyerOut  # 删除
    
    # 改用 assignments
    assignments: List[ContractAssignmentOut]
    primary_lawyer: Optional[LawyerOut]
    
    @staticmethod
    def resolve_assignments(obj):
        return list(obj.assignments.all())
    
    @staticmethod
    def resolve_primary_lawyer(obj):
        assignment = obj.assignments.filter(is_primary=True).first()
        return assignment.lawyer if assignment else None
```

### 4. Service 层更新

```python
# apps/contracts/services/contract_service.py

class ContractService:
    @transaction.atomic
    def create_contract(self, contract_data: Dict[str, Any]) -> Contract:
        # 提取律师 IDs
        lawyer_ids = contract_data.pop("lawyer_ids", [])
        
        if not lawyer_ids:
            raise ValidationException("至少需要指派一个律师")
        
        # 创建合同（不设置 assigned_lawyer）
        contract = Contract.objects.create(**contract_data)
        
        # 创建律师指派（第一个为主办）
        for idx, lawyer_id in enumerate(lawyer_ids):
            ContractAssignment.objects.create(
                contract=contract,
                lawyer_id=lawyer_id,
                is_primary=(idx == 0),  # 第一个为主办
                order=idx
            )
        
        return contract
    
    @transaction.atomic
    def update_contract_lawyers(
        self,
        contract_id: int,
        lawyer_ids: List[int]
    ) -> Contract:
        """更新合同律师指派"""
        contract = self.get_contract(contract_id)
        
        if not lawyer_ids:
            raise ValidationException("至少需要指派一个律师")
        
        # 删除现有指派
        contract.assignments.all().delete()
        
        # 创建新指派
        for idx, lawyer_id in enumerate(lawyer_ids):
            ContractAssignment.objects.create(
                contract=contract,
                lawyer_id=lawyer_id,
                is_primary=(idx == 0),
                order=idx
            )
        
        return contract
```

### 5. API 更新

```python
# apps/contracts/api/contract_api.py

@router.post("/contracts", response=ContractOut)
def create_contract(request, payload: ContractIn):
    service = _get_contract_service()
    
    data = payload.dict()
    # lawyer_ids 已在 data 中
    
    contract = service.create_contract(data)
    return contract


@router.put("/contracts/{contract_id}/lawyers", response=ContractOut)
def update_contract_lawyers(
    request,
    contract_id: int,
    lawyer_ids: List[int]
):
    """更新合同律师指派"""
    service = _get_contract_service()
    contract = service.update_contract_lawyers(contract_id, lawyer_ids)
    return contract
```

## 前端适配

### 修改前
```json
{
  "assigned_lawyer_id": 1,
  "assigned_lawyer_ids": [2, 3]
}
```

### 修改后
```json
{
  "lawyer_ids": [1, 2, 3]  // 第一个为主办律师
}
```

## 优势

1. **简化数据模型** - 只有一个律师指派表
2. **灵活性更高** - 可以轻松调整主办律师
3. **排序支持** - 可以自定义律师显示顺序
4. **代码更清晰** - 减少冗余逻辑

## 风险评估

- **低风险** - 当前没有生产数据
- **向后兼容** - 保留 `assigned_lawyer` 字段
- **测试覆盖** - 需要更新所有相关测试

## 时间估算

- 数据库迁移：30分钟
- 代码更新：2小时
- 测试验证：1小时
- **总计：3.5小时**

## 建议

由于当前没有生产数据，建议立即执行此重构，避免未来数据迁移的复杂性。
