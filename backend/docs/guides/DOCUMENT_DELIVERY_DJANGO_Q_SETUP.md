# 文书送达 Django Q 定时任务设置指南

## 概述

文书送达系统使用 Django Q 来管理定时任务的执行。系统分为两层：

1. **Django Q 调度层**: 定期检查是否有到期的用户定时任务
2. **用户定时任务层**: 用户配置的具体文书查询任务

## 快速设置

### 1. 初始化系统（推荐）

```bash
# 使用默认配置（5分钟检查间隔）
python manage.py init_document_delivery

# 自定义检查间隔
python manage.py init_document_delivery --interval 10

# 查看将要执行的操作（不实际执行）
python manage.py init_document_delivery --dry-run
```

### 2. 手动设置调度

```bash
# 设置 Django Q 调度（5分钟间隔）
python manage.py setup_document_delivery_schedule

# 设置自定义间隔
python manage.py setup_document_delivery_schedule --interval 10

# 移除调度
python manage.py setup_document_delivery_schedule --remove
```

## 系统架构

```
Django Q 调度任务 (每5分钟)
    ↓
execute_document_delivery_schedules 命令
    ↓
检查 DocumentDeliverySchedule 表中的到期任务
    ↓
执行用户配置的文书查询任务
```

## 管理命令说明

### init_document_delivery

一键初始化文书送达系统，设置 Django Q 调度。

**参数:**
- `--interval N`: 设置检查间隔（分钟），默认5分钟
- `--reset`: 重置所有调度任务
- `--dry-run`: 只显示操作，不实际执行

**示例:**
```bash
python manage.py init_document_delivery --interval 10
python manage.py init_document_delivery --reset
```

### setup_document_delivery_schedule

设置或管理 Django Q 调度任务。

**参数:**
- `--interval N`: 执行间隔（分钟），默认5分钟
- `--remove`: 移除现有调度
- `--name NAME`: 调度任务名称
- `--dry-run`: 只显示操作，不实际执行

**示例:**
```bash
python manage.py setup_document_delivery_schedule --interval 15
python manage.py setup_document_delivery_schedule --remove
```

### execute_document_delivery_schedules

执行到期的文书送达定时任务（由 Django Q 调用）。

**参数:**
- `--dry-run`: 只显示任务，不执行
- `--schedule-id ID`: 执行指定任务
- `--force`: 强制执行（忽略是否到期）

**示例:**
```bash
python manage.py execute_document_delivery_schedules --dry-run
python manage.py execute_document_delivery_schedules --schedule-id 123
```

## 运行要求

### 1. 启动 Django Q 集群

```bash
# 启动 Django Q 集群（必须）
python manage.py qcluster
```

### 2. 验证调度状态

```bash
# 检查 Django Q 调度
python manage.py shell -c "
from django_q.models import Schedule
schedules = Schedule.objects.filter(name__icontains='document_delivery')
print(f'Django Q 调度: {schedules.count()} 个')
for s in schedules:
    print(f'- {s.name}: 每 {s.minutes} 分钟执行')
"

# 检查用户定时任务
python manage.py shell -c "
from apps.automation.models import DocumentDeliverySchedule
active = DocumentDeliverySchedule.objects.filter(is_active=True).count()
total = DocumentDeliverySchedule.objects.count()
print(f'用户定时任务: {active}/{total} 个启用')
"
```

## 配置说明

### Django Q 配置

在 `settings.py` 中的 `Q_CLUSTER` 配置：

```python
Q_CLUSTER = {
    'name': 'default',
    'workers': 2,
    'timeout': 600,  # 10分钟超时
    'retry': 1200,   # 20分钟重试
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',
    'max_attempts': 1,
    'catch_up': False,  # 不执行错过的任务
}
```

### 推荐设置

- **检查间隔**: 5-10分钟（平衡及时性和系统负载）
- **用户任务频率**: 根据需要，建议每天1-4次
- **超时设置**: 确保 Django Q 的 timeout 足够长（600秒）

## 故障排除

### 1. 任务不执行

检查项目：
- Django Q 集群是否运行
- 调度任务是否存在
- 用户定时任务是否启用
- 系统时间是否正确

```bash
# 检查调度状态
python manage.py init_document_delivery --dry-run

# 手动执行测试
python manage.py execute_document_delivery_schedules --dry-run
```

### 2. 重置系统

```bash
# 完全重置
python manage.py init_document_delivery --reset
python manage.py init_document_delivery
```

### 3. 查看日志

```bash
# 查看 Django Q 日志
tail -f logs/django_q.log

# 查看应用日志
tail -f logs/automation.log
```

## 监控和维护

### 定期检查

1. **每周检查**: Django Q 调度是否正常运行
2. **每月检查**: 清理过期的任务历史记录
3. **按需调整**: 根据使用情况调整检查间隔

### 性能优化

- 根据用户任务数量调整检查间隔
- 监控 Django Q 队列长度
- 定期清理历史记录

## API 集成

系统也提供 API 接口管理定时任务：

```python
from apps.automation.services.document_delivery.document_delivery_schedule_service import DocumentDeliveryScheduleService

service = DocumentDeliveryScheduleService()

# 设置 Django Q 调度
task_id = service.setup_django_q_schedule(interval_minutes=10)

# 移除调度
count = service.remove_django_q_schedule()
```