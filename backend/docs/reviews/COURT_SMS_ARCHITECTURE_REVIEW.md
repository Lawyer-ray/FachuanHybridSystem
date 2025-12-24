# 法院短信功能架构规范审核报告

**审核日期**: 2025-12-15  
**审核范围**: `apps/automation/services/sms/` 及 `apps/automation/services/chat/` 模块  
**审核标准**: `.kiro/steering/` 规范体系  
**修复 Spec**: `.kiro/specs/court-sms-compliance-fix/`

---

## 审核结论

| 类别 | 状态 | 数量 |
|------|------|------|
| 🔴 严重违规 | 需立即修复 | 4 |
| 🟡 中等违规 | 建议修复 | 4 |
| 🟢 符合规范 | 通过 | 6 |

---

## 🔴 严重违规 (Critical Violations)

### 1. Service 层跨模块直接导入 Model

**违反规范**: `interfaces.md` - "跨模块调用必须通过 ServiceLocator"

**违规位置**:

| 文件 | 行号 | 违规代码 |
|------|------|---------|
| `court_sms_service.py` | 122 | `from apps.cases.models import Case` |
| `court_sms_service.py` | 499 | `from apps.cases.models import CaseLogAttachment` |
| `court_sms_service.py` | 739 | `from apps.organization.models import Lawyer` |
| `court_sms_service.py` | 870 | `from apps.cases.models import CaseNumber` |
| `court_sms_service.py` | 921 | `from apps.cases.services.case_chat_service import CaseChatService` |
| `case_matcher.py` | 159 | `from apps.cases.models import CaseNumber` |
| `case_matcher.py` | 211-212 | `from apps.client.models import Client` / `from apps.cases.models import CaseParty` |
| `case_matcher.py` | 438 | `from apps.organization.models import Lawyer` |
| `sms_parser_service.py` | 210 | `from apps.client.models import Client` |

**修复方案**:
```python
# ❌ 当前代码
from apps.cases.models import Case
case = Case.objects.get(id=case_id)

# ✅ 修复后
from apps.core.interfaces import ServiceLocator
case_service = ServiceLocator.get_case_service()
case_dto = case_service.get_case_internal(case_id)
```

### 2. Admin 层工厂函数未使用 ServiceLocator

**违反规范**: `admin-layer.md` - "使用工厂函数 `_get_admin_service()` 处理复杂操作"

**违规位置**: `court_sms_admin.py` 第21-24行

```python
# ❌ 当前代码
def _get_court_sms_service():
    from apps.automation.services.sms.court_sms_service import CourtSMSService
    return CourtSMSService()  # 直接实例化

# ✅ 修复后
def _get_court_sms_service():
    from apps.core.interfaces import ServiceLocator
    return ServiceLocator.get_court_sms_service()
```

---

## 🟡 中等违规 (Medium Violations)

### 3. Service 层直接实例化跨模块 Service

**违反规范**: `service-layer.md` - "构造函数内直接实例化依赖"

**违规位置**: `court_sms_service.py` 第921-924行

```python
# ❌ 当前代码
from apps.cases.services.case_chat_service import CaseChatService
chat_service = CaseChatService()

# ✅ 修复后
chat_service = self.case_chat_service  # 通过 @property 延迟加载
```

### 4. 缺少 `_xxx_internal()` 内部方法

**违反规范**: `service-layer.md` - "提供 `_xxx_internal()` 内部方法"

`CourtSMSService` 应提供以下内部方法供适配器调用：
- `_submit_sms_internal()`
- `_assign_case_internal()`
- `_get_sms_detail_internal()`

---

## 🟢 符合规范的部分

| 检查项 | 状态 | 说明 |
|--------|------|------|
| API 层工厂函数 | ✅ | 使用 `_get_court_sms_service()` 通过 ServiceLocator |
| 接口定义 | ✅ | 已定义 `ICourtSMSService` 接口 |
| ServiceLocator 注册 | ✅ | 已注册 `get_court_sms_service()` |
| 异常类型 | ✅ | 使用 `ValidationException`、`NotFoundError` |
| 异常参数 | ✅ | 包含 `message`、`code`、`errors` |
| Model 层 | ✅ | 只定义字段和 Meta |

---

## 修复优先级

### P0 - 立即修复
1. `court_sms_admin.py` 工厂函数改用 ServiceLocator
2. `court_sms_service.py` 移除跨模块 Model 直接导入

### P1 - 本周修复
3. `case_matcher.py` 移除跨模块 Model 直接导入
4. `sms_parser_service.py` 移除跨模块 Model 直接导入

### P2 - 下周修复
5. 添加 `_xxx_internal()` 内部方法
6. 完善依赖注入模式

---

## 新增 Steering 规范

已创建 `.kiro/steering/modules/sms-module.md`，包含：
- 跨模块依赖规范
- 正确的调用示例
- Service 层依赖注入模式
- 检查清单

---

## 预防措施

### 代码审查检查点
1. 检查是否有 `from apps.{other_module}.models import` 语句
2. 检查是否有直接实例化跨模块 Service
3. 检查 Admin 层工厂函数是否使用 ServiceLocator

### 自动化检测
建议添加以下测试用例：
```python
def test_no_cross_module_model_imports():
    """检测跨模块 Model 直接导入"""
    # 扫描 sms/ 目录下的所有 .py 文件
    # 检查是否有 from apps.{cases|client|organization|contracts}.models import
```
