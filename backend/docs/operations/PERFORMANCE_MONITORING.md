# 性能监控系统

## 概述

本系统提供全面的性能监控功能，包括：
- API 响应时间监控
- 数据库查询次数监控
- 慢 API 检测
- N+1 查询问题检测
- 性能日志分析

## 功能特性

### 1. 自动监控（中间件）

系统通过中间件自动监控所有 API 请求：

```python
# apiSystem/settings.py
MIDDLEWARE = [
    # ... 其他中间件
    'apps.core.middleware.PerformanceMonitoringMiddleware',
]
```

**监控指标**：
- 响应时间（毫秒）
- 数据库查询次数
- HTTP 状态码
- 用户信息（如果已认证）

**性能阈值**：
- 慢 API 阈值：1000ms
- 最大查询次数：10 次

### 2. 手动监控（装饰器）

对于特定的 Service 方法，可以使用装饰器进行监控：

```python
from apps.core.monitoring import monitor_api

class CaseService:
    @monitor_api("create_case")
    def create_case(self, data, user):
        # 业务逻辑
        pass
```

### 3. 操作监控（上下文管理器）

对于任意代码块，可以使用上下文管理器监控：

```python
from apps.core.monitoring import monitor_operation

with monitor_operation("fetch_external_data"):
    data = fetch_data_from_api()
    process_data(data)
```

## 使用指南

### 启用性能监控

1. **添加中间件**（已配置）：

```python
# apiSystem/settings.py
MIDDLEWARE = [
    # ... 其他中间件
    'apps.core.middleware.PerformanceMonitoringMiddleware',
]
```

2. **启用 DEBUG 模式**（开发环境）：

```python
# apiSystem/settings.py
DEBUG = True  # 仅在开发环境
```

注意：在生产环境中，`DEBUG = False` 时，查询计数功能将被禁用以提高性能。

### 查看性能日志

性能日志记录在 `logs/api.log` 文件中：

```bash
# 查看最新的性能日志
tail -f logs/api.log | grep "metric_type"

# 查看慢 API 日志
tail -f logs/api.log | grep "慢 API"

# 查看性能问题日志
tail -f logs/api.log | grep "性能问题"
```

### 分析性能数据

使用管理命令分析性能日志：

```bash
# 分析最近 24 小时的性能数据
python manage.py analyze_performance

# 分析最近 1 小时的性能数据
python manage.py analyze_performance --hours 1

# 自定义慢 API 阈值（500ms）
python manage.py analyze_performance --threshold 500

# 显示前 20 个慢 API
python manage.py analyze_performance --top 20

# 指定日志文件
python manage.py analyze_performance --log-file logs/api.log
```

**输出示例**：

```
=== 性能分析报告 ===

日志文件: logs/api.log
慢 API 阈值: 1000ms
分析时间范围: 最近 24 小时

=== 最慢的 10 个 API ===

1. POST /api/cases
   调用次数: 150
   平均响应时间: 1250.50ms
   最大响应时间: 3500.00ms
   平均查询次数: 15.2
   错误次数: 2

2. GET /api/contracts
   调用次数: 300
   平均响应时间: 850.30ms
   最大响应时间: 2000.00ms
   平均查询次数: 12.5
   错误次数: 0

=== 查询次数最多的 10 个 API ===

1. GET /api/cases
   调用次数: 500
   平均查询次数: 18.5
   最大查询次数: 35
   平均响应时间: 650.20ms

=== 慢 API 警告（超过 1000ms）===

⚠️  POST /api/cases
   平均响应时间: 1250.50ms
   调用次数: 150

=== 可能存在 N+1 查询问题的 API ===

⚠️  GET /api/cases
   平均查询次数: 18.5
   最大查询次数: 35
   建议: 使用 select_related 或 prefetch_related 优化查询

=== 总体统计 ===

总请求数: 1500
总错误数: 5
错误率: 0.33%
监控的 API 数量: 25
```

## 性能优化建议

### 1. 优化数据库查询

**问题**：N+1 查询

```python
# ❌ 错误：N+1 查询
cases = Case.objects.all()
for case in cases:
    print(case.contract.name)  # 每次循环都查询数据库
```

**解决方案**：使用 `select_related`

```python
# ✅ 正确：使用 select_related
cases = Case.objects.select_related('contract').all()
for case in cases:
    print(case.contract.name)  # 不会额外查询
```

### 2. 优化多对多关系

**问题**：多对多关系的 N+1 查询

```python
# ❌ 错误：N+1 查询
cases = Case.objects.all()
for case in cases:
    for party in case.parties.all():  # 每次循环都查询
        print(party.name)
```

**解决方案**：使用 `prefetch_related`

```python
# ✅ 正确：使用 prefetch_related
cases = Case.objects.prefetch_related('parties').all()
for case in cases:
    for party in case.parties.all():  # 不会额外查询
        print(party.name)
```

### 3. 只查询需要的字段

**问题**：查询所有字段（包括大字段）

```python
# ❌ 错误：查询所有字段
cases = Case.objects.all()
```

**解决方案**：使用 `only()` 或 `defer()`

```python
# ✅ 正确：只查询需要的字段
cases = Case.objects.only('id', 'name', 'current_stage')

# 或者：延迟加载大字段
cases = Case.objects.defer('description', 'notes')
```

### 4. 使用聚合查询

**问题**：在 Python 中计算聚合数据

```python
# ❌ 错误：在 Python 中计算
contracts = Contract.objects.all()
for contract in contracts:
    case_count = contract.cases.count()  # 每次循环都查询
```

**解决方案**：使用 `annotate()`

```python
# ✅ 正确：在数据库层面计算
from django.db.models import Count

contracts = Contract.objects.annotate(
    case_count=Count('cases')
)
for contract in contracts:
    print(contract.case_count)  # 不会额外查询
```

### 5. 批量操作

**问题**：循环中逐个操作

```python
# ❌ 错误：循环中逐个创建
for data in case_data_list:
    Case.objects.create(**data)  # N 次数据库操作
```

**解决方案**：使用批量操作

```python
# ✅ 正确：批量创建
cases = [Case(**data) for data in case_data_list]
Case.objects.bulk_create(cases, batch_size=100)
```

## 性能监控 API

### PerformanceMonitor 类

```python
from apps.core.monitoring import PerformanceMonitor

# 获取查询详情（仅 DEBUG 模式）
queries = PerformanceMonitor.get_query_details()

# 分析查询性能（仅 DEBUG 模式）
analysis = PerformanceMonitor.analyze_queries()
print(f"总查询数: {analysis['total_queries']}")
print(f"总时间: {analysis['total_time_ms']}ms")
print(f"慢查询数: {analysis['slow_query_count']}")
```

### 装饰器

```python
from apps.core.monitoring import monitor_api

@monitor_api("endpoint_name")
def my_function():
    # 业务逻辑
    pass
```

### 上下文管理器

```python
from apps.core.monitoring import monitor_operation

with monitor_operation("operation_name"):
    # 业务逻辑
    pass
```

## 配置选项

### 性能阈值

在 `apps/core/monitoring.py` 中配置：

```python
class PerformanceMonitor:
    # 性能阈值配置
    SLOW_API_THRESHOLD_MS = 1000  # API 响应时间阈值（毫秒）
    SLOW_QUERY_THRESHOLD_MS = 100  # 慢查询阈值（毫秒）
    MAX_QUERY_COUNT = 10  # 最大查询次数阈值
```

### 日志配置

在 `apiSystem/settings.py` 中配置日志：

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/api.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
        },
    },
    'loggers': {
        'apps.core.monitoring': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.core.middleware': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

## 最佳实践

1. **开发环境**：启用 DEBUG 模式，使用性能监控发现问题
2. **生产环境**：关闭 DEBUG 模式，只监控响应时间
3. **定期分析**：每周运行性能分析命令，识别性能瓶颈
4. **优化优先级**：优先优化调用频繁且响应慢的 API
5. **持续监控**：将性能监控集成到 CI/CD 流程中

## 故障排查

### 问题：查询计数为 0

**原因**：DEBUG 模式未启用

**解决方案**：
```python
# apiSystem/settings.py
DEBUG = True  # 仅在开发环境
```

### 问题：日志文件不存在

**原因**：日志目录未创建

**解决方案**：
```bash
mkdir -p logs
```

### 问题：性能头未添加

**原因**：中间件未配置或 DEBUG 模式未启用

**解决方案**：
1. 检查中间件配置
2. 启用 DEBUG 模式

## 相关文档

- [Django 查询优化](https://docs.djangoproject.com/en/stable/topics/db/optimization/)
- [Django 日志配置](https://docs.djangoproject.com/en/stable/topics/logging/)
- [架构设计文档](../../.kiro/specs/backend-architecture-refactoring/design.md)
