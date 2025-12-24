# Token获取性能优化功能

## 概述

本文档描述了为自动Token获取服务实现的性能优化和监控功能，包括Redis缓存、性能监控、统计报告和并发优化。

## 功能特性

### 1. Redis缓存管理

**文件**: `apps/automation/services/token/cache_manager.py`

**功能**:
- Token缓存：避免重复获取有效Token
- 账号凭证缓存：减少数据库查询
- 登录统计缓存：提升性能分析速度
- 黑名单缓存：快速过滤失败账号

**使用示例**:
```python
from apps.automation.services.token.cache_manager import cache_manager

# 缓存Token
cache_manager.cache_token("court_zxfw", "test_account", "token_12345")

# 获取缓存的Token
token = cache_manager.get_cached_token("court_zxfw", "test_account")
```

### 2. 性能监控

**文件**: `apps/automation/services/token/performance_monitor.py`

**功能**:
- 实时性能指标收集
- 统计报告生成
- 性能告警
- 缓存性能监控

**监控指标**:
- 总获取次数
- 成功/失败次数
- 成功率
- 平均耗时
- 并发数
- 缓存命中率

### 3. 并发优化

**文件**: `apps/automation/services/token/concurrency_optimizer.py`

**功能**:
- 智能并发控制
- 资源使用监控
- 队列管理
- 死锁检测和恢复

**配置参数**:
```python
@dataclass
class ConcurrencyConfig:
    max_concurrent_acquisitions: int = 3  # 最大并发获取数
    max_concurrent_per_site: int = 2      # 每个站点最大并发数
    max_concurrent_per_account: int = 1   # 每个账号最大并发数
    acquisition_timeout: float = 300.0    # 获取超时时间（秒）
```

### 4. 历史记录

**文件**: `apps/automation/services/token/history_recorder.py`

**功能**:
- Token获取历史记录
- 统计分析支持
- 性能数据持久化

**数据模型**: `TokenAcquisitionHistory`

## API接口

### 性能监控API

**基础路径**: `/api/v1/automation/performance/`

**端点**:
- `GET /metrics` - 获取实时性能指标
- `GET /statistics` - 获取统计报告
- `GET /health` - 健康检查
- `GET /resource-usage` - 获取资源使用情况
- `POST /optimize-concurrency` - 优化并发配置
- `GET /cache-stats` - 获取缓存统计
- `POST /cache/warm-up` - 预热缓存
- `DELETE /cache/clear` - 清除缓存
- `POST /metrics/reset` - 重置性能指标
- `POST /resources/cleanup` - 清理资源

### 使用示例

```bash
# 获取性能指标
curl http://localhost:8000/api/v1/automation/performance/metrics

# 健康检查
curl http://localhost:8000/api/v1/automation/performance/health

# 预热缓存
curl -X POST "http://localhost:8000/api/v1/automation/performance/cache/warm-up?site_name=court_zxfw"
```

## 管理命令

### optimize_token_performance

**用途**: Token获取服务性能优化和维护

**使用方法**:
```bash
# 执行健康检查
python manage.py optimize_token_performance --health-check

# 清理30天前的历史记录
python manage.py optimize_token_performance --cleanup-days 30

# 预热指定网站缓存
python manage.py optimize_token_performance --warm-cache court_zxfw

# 分析并发配置
python manage.py optimize_token_performance --optimize-concurrency

# 重置性能指标
python manage.py optimize_token_performance --reset-metrics

# 组合使用
python manage.py optimize_token_performance --health-check --cleanup-days 7 --warm-cache court_zxfw
```

## 集成说明

### 1. 自动Token获取服务集成

性能优化功能已集成到 `AutoTokenAcquisitionService` 中：

- 自动记录性能监控数据
- 使用缓存减少数据库查询
- 应用并发控制
- 记录历史数据

### 2. 账号选择策略集成

`AccountSelectionStrategy` 已集成缓存功能：

- 缓存账号凭证列表
- 缓存黑名单
- 缓存账号统计信息

## 配置要求

### Redis配置

确保在 `settings.py` 中正确配置Redis：

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/0",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}
```

### 环境变量

可选的环境变量配置：

```bash
REDIS_URL=redis://localhost:6379/0
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_password
```

## 监控和告警

### 告警阈值

默认告警阈值（可配置）：

```python
@dataclass
class AlertThresholds:
    min_success_rate: float = 80.0      # 最低成功率（%）
    max_avg_duration: float = 120.0     # 最大平均耗时（秒）
    max_timeout_rate: float = 10.0      # 最大超时率（%）
    max_concurrent_acquisitions: int = 5 # 最大并发获取数
    min_cache_hit_rate: float = 70.0    # 最低缓存命中率（%）
```

### 健康状态

系统健康状态分为：
- `healthy` - 健康，无告警
- `warning` - 警告，有低级别告警
- `degraded` - 降级，有中级别告警
- `unhealthy` - 不健康，有高级别告警

## 性能优化建议

### 1. 缓存策略

- 定期预热常用网站的缓存
- 监控缓存命中率，目标 > 70%
- 合理设置缓存过期时间

### 2. 并发控制

- 根据系统负载调整并发数
- 监控队列积压情况
- 避免过度并发导致资源竞争

### 3. 历史数据管理

- 定期清理旧的历史记录（建议保留30天）
- 监控数据库存储空间
- 考虑数据归档策略

### 4. 监控和告警

- 设置合适的告警阈值
- 定期检查系统健康状态
- 建立性能基线和趋势分析

## 故障排查

### 常见问题

1. **缓存连接失败**
   - 检查Redis服务状态
   - 验证连接配置
   - 查看网络连通性

2. **性能指标异常**
   - 检查并发配置
   - 分析历史数据趋势
   - 查看系统资源使用情况

3. **并发控制问题**
   - 检查锁状态
   - 清理过期资源
   - 调整并发参数

### 日志分析

关键日志位置：
- 性能监控：`apps.automation.services.token.performance_monitor`
- 缓存管理：`apps.automation.services.token.cache_manager`
- 并发优化：`apps.automation.services.token.concurrency_optimizer`

## 测试

### 单元测试

运行性能优化相关测试：

```bash
python -m pytest tests/unit/automation/test_performance_optimization.py -v
```

### 功能测试

```bash
# 测试基本功能
python manage.py shell -c "
from apps.automation.services.token.performance_monitor import performance_monitor
from apps.automation.services.token.cache_manager import cache_manager

# 测试性能监控
performance_monitor.record_acquisition_start('test_001', 'court_zxfw', 'test_account')
performance_monitor.record_acquisition_end('test_001', True, 10.5, 8.2)
print('性能监控测试完成')

# 测试缓存
cache_manager.cache_token('court_zxfw', 'test_account', 'test_token')
token = cache_manager.get_cached_token('court_zxfw', 'test_account')
print(f'缓存测试完成: {token}')
"
```

## 总结

Token获取性能优化功能提供了全面的性能监控、缓存管理和并发优化能力，显著提升了系统的性能和可靠性。通过合理配置和定期维护，可以确保系统在高负载情况下的稳定运行。