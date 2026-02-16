# Cases 模块 Mypy 类型错误分析报告

## 执行命令
```bash
mypy apps/cases/ --strict
```

## 总体统计

- **总错误数**: 462 个
- **涉及文件数**: 约 50+ 个文件
- **主要模块**: services, api, admin

## 错误类型分布

| 排名 | 错误类型 | 数量 | 占比 | 说明 |
|------|---------|------|------|------|
| 1 | `type-arg` | 150 | 32.5% | 泛型类型参数缺失（如 `dict`, `list`, `QuerySet`） |
| 2 | `no-untyped-def` | 137 | 29.7% | 函数缺少类型注解 |
| 3 | `attr-defined` | 75 | 16.2% | 属性未定义（主要是 Django Model 动态属性） |
| 4 | `no-any-return` | 40 | 8.7% | 函数返回 Any 类型 |
| 5 | `no-untyped-call` | 20 | 4.3% | 调用未类型化的函数 |
| 6 | `arg-type` | 6 | 1.3% | 参数类型不兼容 |
| 7 | `override` | 6 | 1.3% | 方法重写类型不兼容 |
| 8 | `call-arg` | 4 | 0.9% | 函数调用参数错误 |
| 9 | `return-value` | 3 | 0.6% | 返回值类型不兼容 |
| 10 | `assignment` | 3 | 0.6% | 赋值类型不兼容 |
| 其他 | - | 18 | 3.9% | 其他类型错误 |

## 文件错误分布（Top 15）

| 排名 | 文件路径 | 错误数 |
|------|---------|--------|
| 1 | `services/case_service.py` | 25 |
| 2 | `services/caselog_service.py` | 23 |
| 3 | `services/log/caselog_service.py` | 20 |
| 4 | `services/case_access_service.py` | 18 |
| 5 | `services/template/folder_binding_service.py` | 17 |
| 6 | `services/number/case_number_service.py` | 17 |
| 7 | `services/chat/case_chat_service.py` | 17 |
| 8 | `services/data/cause_court_data_service.py` | 16 |
| 9 | `api/caseparty_api.py` | 16 |
| 10 | `api/casenumber_api.py` | 16 |
| 11 | `services/party/case_party_service.py` | 15 |
| 12 | `api/case_api.py` | 14 |
| 13 | `api/caseaccess_api.py` | 14 |
| 14 | `services/template/case_template_generation_service.py` | 13 |
| 15 | `services/template/case_document_template_admin_service.py` | 12 |

## 主要问题分析

### 1. 泛型类型参数缺失 (150 个错误, 32.5%)

**问题描述**: 使用 `dict`, `list`, `QuerySet` 等泛型类型时未指定类型参数

**典型错误**:
```python
# ❌ 错误
org_access: dict | None = None
parties_qs: QuerySet

# ✅ 正确
org_access: dict[str, Any] | None = None
parties_qs: QuerySet[CaseParty]
```

**修复策略**:
- `dict` → `dict[str, Any]`
- `list` → `list[Any]` 或具体类型如 `list[str]`
- `QuerySet` → `QuerySet[ModelName]`

### 2. 函数缺少类型注解 (137 个错误, 29.7%)

**问题描述**: 函数参数或返回值缺少类型注解

**典型错误**:
```python
# ❌ 错误
def list_logs(self, case_id, user, org_access=None):
    pass

# ✅ 正确
def list_logs(
    self,
    case_id: int,
    user: Any,
    org_access: dict[str, Any] | None = None
) -> QuerySet[CaseLog]:
    pass
```

**修复策略**:
- 为所有函数参数添加类型注解
- 为所有函数添加返回类型注解
- 使用 `-> None` 表示无返回值

### 3. Django Model 动态属性 (75 个错误, 16.2%)

**问题描述**: Django Model 的动态属性（如 `id`, `case_id`）在类型检查时不存在

**典型错误**:
```python
# ❌ 错误
log_id = log.id  # "CaseLog" has no attribute "id"
```

**修复策略**:

**方案 A**: 使用类型存根（推荐）
```python
# apps/cases/models.pyi
class CaseLog(models.Model):
    id: int
    case_id: int
    case: Case
    # ... 其他字段
```

**方案 B**: 使用 cast()
```python
from typing import cast
log_id = cast(int, log.id)
```

**方案 C**: 使用 getattr()
```python
log_id = getattr(log, 'id')
```

### 4. 函数返回 Any 类型 (40 个错误, 8.7%)

**问题描述**: 函数声明返回具体类型，但实际返回 Any

**典型错误**:
```python
# ❌ 错误
def get_party(self, party_id: int) -> CaseParty:
    return self.query_facade.get_party(party_id)  # 返回 Any
```

**修复策略**:
- 确保被调用函数有正确的返回类型注解
- 使用 `cast()` 进行类型转换
- 修正函数的实际返回类型

### 5. 调用未类型化的函数 (20 个错误, 4.3%)

**问题描述**: 在类型化的上下文中调用未类型化的函数

**典型错误**:
```python
# ❌ 错误
service = _get_case_access_service()  # 工厂函数缺少返回类型
```

**修复策略**:
```python
# ✅ 正确
def _get_case_access_service() -> CaseAccessService:
    from ..services import CaseAccessService
    return CaseAccessService()
```

## 修复优先级建议

### 高优先级（快速修复，影响大）

1. **泛型类型参数** (150 个)
   - 批量替换 `dict` → `dict[str, Any]`
   - 批量替换 `list` → `list[Any]`
   - 手动修复 `QuerySet` → `QuerySet[Model]`
   - 预计时间: 2-3 小时

2. **函数类型注解** (137 个)
   - 为 API 层函数添加类型注解
   - 为 Service 层函数添加类型注解
   - 预计时间: 1-2 天

### 中优先级（需要仔细处理）

3. **Django Model 动态属性** (75 个)
   - 创建 `models.pyi` 类型存根文件
   - 为常用 Model 添加类型定义
   - 预计时间: 4-6 小时

4. **函数返回 Any** (40 个)
   - 修正函数返回类型注解
   - 使用 cast() 处理必要的情况
   - 预计时间: 4-6 小时

### 低优先级（逐个修复）

5. **其他错误** (60 个)
   - 参数类型不兼容
   - 返回值类型不兼容
   - 方法重写问题
   - 预计时间: 1-2 天

## 预计修复时间

- **快速修复阶段**: 1-2 天（泛型类型参数 + 部分函数注解）
- **完整修复阶段**: 3-5 天（所有错误修复完成）
- **验证测试阶段**: 1 天（确保无回归）

**总计**: 5-8 天可完成 cases 模块的类型错误修复

## 修复脚本建议

可以创建以下批量修复脚本：

1. `fix_generic_types_cases.py` - 修复泛型类型参数
2. `fix_function_annotations_cases.py` - 添加函数类型注解
3. `create_cases_model_stubs.py` - 创建 Model 类型存根

## 注意事项

1. 修复前先运行测试建立基线
2. 每个批次修复后运行测试验证
3. 使用 git commit 分批提交，便于回滚
4. 优先修复核心 Service 层，再修复 API 层
5. Model 类型存根文件需要与实际 Model 定义保持同步
