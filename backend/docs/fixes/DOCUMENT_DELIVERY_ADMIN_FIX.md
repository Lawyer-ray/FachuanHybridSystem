# 文书送达 Django Admin 字段错误修复

## 问题描述

在访问文书送达定时任务的 Django Admin 界面时，出现以下错误：

```
FieldError: Cannot resolve keyword 'username' into field. 
Choices are: account, created_at, delivery_schedules, document_query_histories, id, is_preferred, 
last_login_success_at, lawyer, lawyer_id, login_failure_count, login_success_count, password, 
site_name, updated_at, url.
```

## 根本原因

Django Admin 配置中使用了错误的字段名：
- 错误使用：`credential__username`
- 正确字段：`credential__account`

AccountCredential 模型的字段结构：
- ✅ `account` - 账号字段
- ❌ `username` - 不存在的字段

## 修复内容

### 1. DocumentDeliveryScheduleAdmin 修复

**文件**: `backend/apps/automation/admin/document_delivery/document_delivery_schedule_admin.py`

**修复项目**:
- `search_fields`: `credential__username` → `credential__account`
- `credential_display()` 方法: `obj.credential.username` → `obj.credential.account`
- `formfield_for_foreignkey()` 方法: `order_by('site_name', 'username')` → `order_by('site_name', 'account')`

### 2. DocumentQueryHistoryAdmin 修复

**文件**: `backend/apps/automation/admin/document_delivery/document_query_history_admin.py`

**修复项目**:
- `search_fields`: `credential__username` → `credential__account`
- `credential_display()` 方法: `obj.credential.username` → `obj.credential.account`

## 验证结果

### 1. 系统检查通过
```bash
python manage.py check
# System check identified no issues (0 silenced).
```

### 2. Admin 配置加载成功
```python
from apps.automation.admin.document_delivery.document_delivery_schedule_admin import DocumentDeliveryScheduleAdmin
# Admin configuration loaded successfully!
```

### 3. 功能测试通过
- ✅ 定时任务创建
- ✅ Admin 显示方法
- ✅ 搜索功能
- ✅ 字段过滤

## 影响范围

**修复前**: Django Admin 界面无法访问，出现字段解析错误
**修复后**: Django Admin 界面正常工作，支持完整的管理功能

## 相关文件

- `backend/apps/automation/admin/document_delivery/document_delivery_schedule_admin.py`
- `backend/apps/automation/admin/document_delivery/document_query_history_admin.py`
- `backend/apps/organization/models.py` (AccountCredential 模型定义)

## 预防措施

1. **字段名验证**: 在编写 Admin 配置时，确认模型字段名的正确性
2. **系统检查**: 定期运行 `python manage.py check` 验证配置
3. **测试覆盖**: 为 Admin 界面添加自动化测试

## 测试命令

```bash
# 系统检查
python manage.py check

# Admin 配置测试
python manage.py shell -c "
from apps.automation.admin.document_delivery.document_delivery_schedule_admin import DocumentDeliveryScheduleAdmin
from apps.automation.models import DocumentDeliverySchedule
from django.contrib.admin.sites import AdminSite
admin = DocumentDeliveryScheduleAdmin(DocumentDeliverySchedule, AdminSite())
print('Admin loaded successfully:', admin.search_fields)
"

# 功能测试
python manage.py shell -c "
from apps.automation.services.document_delivery.document_delivery_schedule_service import DocumentDeliveryScheduleService
from apps.organization.models import AccountCredential
credential = AccountCredential.objects.first()
if credential:
    service = DocumentDeliveryScheduleService()
    schedule = service.create_schedule(credential.id, 1, 24, 24, True)
    print('Schedule created:', schedule.id)
    schedule.delete()
    print('Test completed successfully')
"
```