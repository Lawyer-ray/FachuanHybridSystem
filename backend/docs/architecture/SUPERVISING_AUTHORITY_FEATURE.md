# 主管机关功能实现

## 实现日期
2025-11-30

## 需求
1. 删除案件的 4 个旧字段：侦查机关、审查起诉机关、当前关押地点、审理机构
2. 新增主管机关模型，一个案件可以关联多个主管机关
3. 主管机关有两个字段：名称、性质（单选）
4. 两个字段都是选填，可为空
5. 完善 API 和 Django Admin 展示

## 实现方案

### 1. 数据模型

#### 新增 AuthorityType 枚举

```python
class AuthorityType(models.TextChoices):
    """主管机关性质"""
    INVESTIGATION = "investigation", _("侦查机关")
    PROSECUTION = "prosecution", _("审查起诉机关")
    TRIAL = "trial", _("审理机构")
    DETENTION = "detention", _("当前关押地点")
```

#### 新增 SupervisingAuthority 模型

```python
class SupervisingAuthority(models.Model):
    """主管机关"""
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name="supervising_authorities",
        verbose_name=_("案件")
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("名称")
    )
    authority_type = models.CharField(
        max_length=32,
        choices=AuthorityType.choices,
        default=AuthorityType.TRIAL,
        blank=True,
        null=True,
        verbose_name=_("性质")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
```

#### 从 Case 模型删除的字段

- `investigation_agency` (侦查机关)
- `prosecution_review_agency` (审查起诉机关)
- `detention_location` (当前关押地点)
- `hearing_institution` (审理机构)

### 2. 数据库迁移

**迁移文件**: `0027_remove_case_detention_location_and_more.py`

操作：
- 删除 4 个旧字段
- 创建 SupervisingAuthority 模型

### 3. API Schema

#### SupervisingAuthorityIn

```python
class SupervisingAuthorityIn(Schema):
    name: Optional[str] = None
    authority_type: Optional[str] = None
```

#### SupervisingAuthorityOut

```python
class SupervisingAuthorityOut(ModelSchema, SchemaMixin):
    authority_type_display: str | None
    class Meta:
        model = SupervisingAuthority
        fields = ["id", "name", "authority_type", "created_at"]
```

#### SupervisingAuthorityUpdate

```python
class SupervisingAuthorityUpdate(Schema):
    name: Optional[str] = None
    authority_type: Optional[str] = None
```

#### 修改 CaseOut

添加 `supervising_authorities` 字段：

```python
class CaseOut(ModelSchema):
    supervising_authorities: List["SupervisingAuthorityOut"]
    # ...
```

#### 修改 CaseCreateFull

添加 `supervising_authorities` 字段：

```python
class CaseCreateFull(Schema):
    case: CaseIn
    parties: Optional[list[CasePartyCreate]] = None
    assignments: Optional[list[CaseAssignmentCreate]] = None
    logs: Optional[list[CaseLogCreate]] = None
    case_numbers: Optional[list[CaseNumberIn]] = None
    supervising_authorities: Optional[list[SupervisingAuthorityIn]] = None
```

### 4. Django Admin

#### SupervisingAuthorityInline

```python
class SupervisingAuthorityInline(BaseTabularInline):
    """主管机关内联"""
    model = SupervisingAuthority
    extra = 1
    fields = ("name", "authority_type")
```

#### 添加到 CaseAdmin

```python
@admin.register(Case)
class CaseAdmin(BaseModelAdmin):
    inlines = [
        CasePartyInline,
        CaseAssignmentInline,
        SupervisingAuthorityInline,  # 新增
        CaseNumberInline,
        CaseLogInline
    ]
```

### 5. Service 层

#### CaseService.create_case_full

添加主管机关创建逻辑：

```python
# 创建主管机关
supervising_authorities = []
for authority in supervising_authorities_data:
    from ..models import SupervisingAuthority
    supervising_authorities.append(SupervisingAuthority.objects.create(
        case=case,
        name=authority.get("name"),
        authority_type=authority.get("authority_type"),
    ))

return {
    "case": case,
    "parties": parties,
    "assignments": assignments,
    "logs": logs,
    "supervising_authorities": supervising_authorities,
}
```

## 使用示例

### 1. Django Admin

在案件详情页，可以看到"主管机关"内联表格：

| 名称 | 性质 |
|------|------|
| 北京市公安局 | 侦查机关 |
| 北京市人民检察院 | 审查起诉机关 |
| 北京市第一中级人民法院 | 审理机构 |

### 2. API 创建案件

```json
POST /api/v1/cases/full
{
  "case": {
    "name": "张三诉李四合同纠纷案",
    "status": "active",
    "cause_of_action": "合同纠纷",
    "target_amount": 100000
  },
  "parties": [...],
  "assignments": [...],
  "supervising_authorities": [
    {
      "name": "北京市第一中级人民法院",
      "authority_type": "trial"
    },
    {
      "name": "北京市看守所",
      "authority_type": "detention"
    }
  ]
}
```

### 3. API 响应

```json
{
  "case": {
    "id": 1,
    "name": "张三诉李四合同纠纷案",
    ...
  },
  "parties": [...],
  "assignments": [...],
  "logs": [],
  "case_numbers": [],
  "supervising_authorities": [
    {
      "id": 1,
      "name": "北京市第一中级人民法院",
      "authority_type": "trial",
      "authority_type_display": "审理机构",
      "created_at": "2025-11-30T14:59:33Z"
    },
    {
      "id": 2,
      "name": "北京市看守所",
      "authority_type": "detention",
      "authority_type_display": "当前关押地点",
      "created_at": "2025-11-30T14:59:33Z"
    }
  ]
}
```

## 特性

### 1. 灵活性
- 一个案件可以关联多个主管机关
- 支持不同性质的机关（侦查、起诉、审理、关押）

### 2. 可选性
- 名称和性质都是可选的
- 可以只填写名称，不选择性质
- 可以只选择性质，不填写名称

### 3. 默认值
- 性质默认为"审理机构"（最常用）

### 4. 排序
- 按创建时间排序，先创建的在前

### 5. 显示
- `__str__` 方法智能显示：
  - 有名称和性质：显示"性质 - 名称"
  - 只有名称：显示名称
  - 只有性质：显示性质
  - 都没有：显示"主管机关 #ID"

## 数据迁移注意事项

### 旧数据处理

如果数据库中已有案件数据，旧的 4 个字段的数据会在迁移时丢失。如果需要保留，应该：

1. 在迁移前导出数据
2. 应用迁移
3. 编写脚本将旧数据转换为 SupervisingAuthority 记录

示例脚本：

```python
from apps.cases.models import Case, SupervisingAuthority

# 假设已导出旧数据到 old_data.json
for case_id, old_data in old_data_dict.items():
    case = Case.objects.get(id=case_id)
    
    if old_data.get('investigation_agency'):
        SupervisingAuthority.objects.create(
            case=case,
            name=old_data['investigation_agency'],
            authority_type='investigation'
        )
    
    if old_data.get('prosecution_review_agency'):
        SupervisingAuthority.objects.create(
            case=case,
            name=old_data['prosecution_review_agency'],
            authority_type='prosecution'
        )
    
    if old_data.get('hearing_institution'):
        SupervisingAuthority.objects.create(
            case=case,
            name=old_data['hearing_institution'],
            authority_type='trial'
        )
    
    if old_data.get('detention_location'):
        SupervisingAuthority.objects.create(
            case=case,
            name=old_data['detention_location'],
            authority_type='detention'
        )
```

## 相关文件

- `backend/apps/cases/models.py` - 数据模型
- `backend/apps/cases/schemas.py` - API Schema
- `backend/apps/cases/admin/case_admin.py` - Django Admin
- `backend/apps/cases/services/case_service.py` - Service 层
- `backend/apps/cases/api/case_api.py` - API 路由
- `backend/apps/cases/migrations/0027_remove_case_detention_location_and_more.py` - 数据库迁移

## 测试清单

- [x] 创建 SupervisingAuthority 模型
- [x] 删除 Case 模型的 4 个旧字段
- [x] 生成并应用数据库迁移
- [x] 添加 API Schema
- [x] 修改 CaseService.create_case_full
- [x] 添加 Django Admin Inline
- [ ] 测试 API 创建案件（包含主管机关）
- [ ] 测试 Django Admin 创建案件
- [ ] 测试主管机关的增删改查
- [ ] 验证字段可选性
- [ ] 验证默认值

## 总结

成功实现了主管机关功能，将原来的 4 个固定字段改为灵活的多对一关系，提高了系统的扩展性和灵活性。现在一个案件可以关联任意数量的主管机关，每个主管机关都有名称和性质两个可选字段。
