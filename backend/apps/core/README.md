# ⚙️ 核心模块 (Core)

核心模块，提供全局配置、异常处理、接口定义、验证器、缓存、日志、监控等基础功能。

## 📚 模块概述

本模块是整个系统的基础设施层，提供：
- 全局配置管理
- 统一异常处理
- 接口定义（Protocol）
- 数据验证器
- 缓存管理
- 日志管理
- 性能监控
- 健康检查
- API 限流

## 📁 目录结构

```
core/
├── api.py              # API 全局配置
├── cache.py            # 缓存管理
├── config.py           # 配置管理
├── exceptions.py       # 异常定义
├── health.py           # 健康检查
├── interfaces.py       # 接口定义（Protocol）
├── logging.py          # 日志配置
├── middleware.py       # 中间件
├── monitoring.py       # 性能监控
├── schemas.py          # 通用 Schemas
├── throttling.py       # API 限流
├── validators.py       # 数据验证器
└── management/         # Django 管理命令
    └── commands/
        ├── analyze_performance.py      # 性能分析
        └── check_db_performance.py     # 数据库性能检查
```

## 🔑 核心功能

### 配置管理
- ✅ 集中配置管理（config.py）
- ✅ 环境变量支持
- ✅ 配置验证
- ✅ 配置热更新

### 异常处理
- ✅ 统一异常体系
- ✅ 业务异常（BusinessException）
- ✅ 验证异常（ValidationException）
- ✅ 权限异常（PermissionDenied）
- ✅ 资源不存在异常（NotFoundError）
- ✅ 冲突异常（ConflictError）

### 接口定义
- ✅ Protocol 接口定义
- ✅ DTO 数据传输对象
- ✅ 跨模块通信接口
- ✅ 事件总线（EventBus）

### 数据验证
- ✅ 通用验证器
- ✅ 身份证号验证
- ✅ 电话号码验证
- ✅ 邮箱验证
- ✅ 自定义验证规则

### 缓存管理
- ✅ Redis 缓存
- ✅ 缓存装饰器
- ✅ 缓存失效策略
- ✅ 缓存预热

### 日志管理
- ✅ 结构化日志
- ✅ 日志级别管理
- ✅ 日志轮转
- ✅ 日志聚合

### 性能监控
- ✅ 请求耗时监控
- ✅ 数据库查询监控
- ✅ 缓存命中率监控
- ✅ 性能指标收集

## 🚀 快速开始

### 1. 配置管理

```python
from apps.core.config import app_config

# 访问配置
database_config = app_config.database
cache_config = app_config.cache
business_config = app_config.business

# 使用配置
page_size = business_config.default_page_size
max_upload_size = business_config.max_upload_size
```

### 2. 异常处理

```python
from apps.core.exceptions import (
    ValidationException,
    PermissionDenied,
    NotFoundError,
    ConflictError
)

# 抛出业务异常
def create_resource(data, user):
    # 权限检查
    if not user.has_perm('resources.add_resource'):
        raise PermissionDenied(
            message="无权限创建资源",
            code="PERMISSION_DENIED"
        )
    
    # 数据验证
    if Resource.objects.filter(name=data.name).exists():
        raise ValidationException(
            message="资源名称已存在",
            code="DUPLICATE_NAME",
            errors={"name": "该名称已被使用"}
        )
    
    # 资源不存在
    if not Dependency.objects.filter(id=data.dependency_id).exists():
        raise NotFoundError(
            message="依赖不存在",
            code="DEPENDENCY_NOT_FOUND"
        )
    
    # 资源冲突
    if resource.status == 'archived':
        raise ConflictError(
            message="已归档的资源无法修改",
            code="RESOURCE_ARCHIVED"
        )
```

### 3. 接口定义

```python
from apps.core.interfaces import IContractService, ContractDTO
from typing import Protocol, Optional

# 定义接口
class IResourceService(Protocol):
    """资源服务接口"""
    
    def get_resource(self, resource_id: int) -> Optional[ResourceDTO]:
        """获取资源"""
        ...
    
    def create_resource(self, data: ResourceCreateSchema) -> ResourceDTO:
        """创建资源"""
        ...

# 使用接口
class CaseService:
    """案件服务"""
    
    def __init__(self, contract_service: IContractService):
        """注入接口依赖"""
        self.contract_service = contract_service
    
    def create_case(self, data, user):
        # 通过接口调用
        contract = self.contract_service.get_contract(data.contract_id)
        if not contract:
            raise ValidationException("合同不存在")
        
        # 业务逻辑...
```

### 4. 缓存使用

```python
from apps.core.cache import cache_result

# 使用缓存装饰器
@cache_result(timeout=300)  # 缓存 5 分钟
def get_case_statistics(case_id: int):
    """获取案件统计（耗时计算）"""
    # 复杂计算...
    return statistics

# 手动缓存
from django.core.cache import cache

# 设置缓存
cache.set('key', 'value', timeout=300)

# 获取缓存
value = cache.get('key')

# 删除缓存
cache.delete('key')
```

### 5. 数据验证

```python
from apps.core.validators import (
    validate_phone,
    validate_email,
    validate_id_number
)

# 验证电话号码
try:
    validate_phone("13800138000")
except ValidationError as e:
    print(f"电话号码无效: {e}")

# 验证邮箱
try:
    validate_email("user@example.com")
except ValidationError as e:
    print(f"邮箱无效: {e}")

# 验证身份证号
try:
    validate_id_number("110101199001011234")
except ValidationError as e:
    print(f"身份证号无效: {e}")
```

### 6. 日志记录

```python
import logging

logger = logging.getLogger("apps.module")

# 结构化日志
logger.info(
    "操作成功",
    extra={
        "action": "create_resource",
        "resource_id": resource.id,
        "user_id": user.id,
        "duration_ms": duration
    }
)

# 错误日志（包含堆栈）
try:
    result = dangerous_operation()
except Exception as e:
    logger.error(
        f"操作失败: {e}",
        exc_info=True,  # 记录完整堆栈
        extra={
            "action": "dangerous_operation",
            "user_id": user.id
        }
    )
    raise
```

### 7. 性能监控

```python
from apps.core.monitoring import monitor_performance

# 使用装饰器监控性能
@monitor_performance
def expensive_operation():
    """耗时操作"""
    # 复杂计算...
    return result

# 手动记录性能指标
from apps.core.monitoring import record_metric

record_metric(
    metric_name="api_response_time",
    value=duration_ms,
    tags={"endpoint": "/api/cases", "method": "GET"}
)
```

### 8. 健康检查

```bash
# 检查系统健康状态
curl http://localhost:8000/api/health

# 响应示例
{
  "status": "healthy",
  "database": "ok",
  "cache": "ok",
  "disk_space": "ok",
  "memory": "ok"
}
```

## 📊 异常体系

```
BusinessException (基类)
├── ValidationException (400)
│   └── 数据验证失败
├── AuthenticationError (401)
│   └── 认证失败
├── PermissionDenied (403)
│   └── 权限不足
├── NotFoundError (404)
│   └── 资源不存在
├── ConflictError (409)
│   └── 资源冲突
├── RateLimitError (429)
│   └── 频率限制
└── ExternalServiceError (502)
    └── 外部服务错误
```

## 🔒 接口定义规范

### Protocol 定义
```python
from typing import Protocol, Optional

class IService(Protocol):
    """服务接口"""
    
    def method(self, param: int) -> Optional[DTO]:
        """方法说明"""
        ...
```

### DTO 定义
```python
from dataclasses import dataclass

@dataclass
class ResourceDTO:
    """资源数据传输对象"""
    id: int
    name: str
    status: str
    
    @classmethod
    def from_model(cls, resource) -> "ResourceDTO":
        """从 Model 转换为 DTO"""
        return cls(
            id=resource.id,
            name=resource.name,
            status=resource.status
        )
```

## 🧪 测试

```bash
# 运行单元测试
cd backend
source venv311/bin/activate
python -m pytest tests/unit/test_core/ -v

# 运行集成测试
python -m pytest tests/integration/test_core/ -v

# 运行属性测试
python -m pytest tests/property/test_core_properties/ -v
```

## 📝 相关文档

- **[config.py](config.py)** - 配置管理
- **[exceptions.py](exceptions.py)** - 异常定义
- **[interfaces.py](interfaces.py)** - 接口定义
- **[validators.py](validators.py)** - 数据验证器
- **[cache.py](cache.py)** - 缓存管理
- **[logging.py](logging.py)** - 日志配置
- **[monitoring.py](monitoring.py)** - 性能监控
- **[PERFORMANCE_MONITORING.md](PERFORMANCE_MONITORING.md)** - 性能监控文档

## 🔗 依赖模块

本模块是基础设施层，被所有其他模块依赖：
- **cases**: 案件模块
- **contracts**: 合同模块
- **client**: 客户模块
- **organization**: 组织模块
- **automation**: 自动化模块

## 🎯 最佳实践

### 1. 使用配置管理
```python
# ✅ 正确：使用配置类
from apps.core.config import app_config

page_size = app_config.business.default_page_size

# ❌ 错误：硬编码配置
page_size = 20
```

### 2. 抛出业务异常
```python
# ✅ 正确：抛出自定义异常
if not user.has_perm('resource.add'):
    raise PermissionDenied("无权限")

# ❌ 错误：返回错误码
if not user.has_perm('resource.add'):
    return {"error": "无权限"}, 403
```

### 3. 使用接口解耦
```python
# ✅ 正确：依赖接口
def __init__(self, service: IService):
    self.service = service

# ❌ 错误：依赖具体实现
def __init__(self, service: ConcreteService):
    self.service = service
```

### 4. 结构化日志
```python
# ✅ 正确：使用 extra 参数
logger.info("操作成功", extra={"user_id": 1})

# ❌ 错误：字符串拼接
logger.info(f"用户 {user_id} 操作成功")
```

## 🐛 常见问题

### Q1: 如何添加新的配置项？
**A**: 在 `config.py` 的相应配置类中添加字段，并提供默认值。

### Q2: 如何自定义异常？
**A**: 继承 `BusinessException` 基类，定义新的异常类型。

### Q3: 如何定义新的接口？
**A**: 在 `interfaces.py` 中使用 `Protocol` 定义接口。

## 📈 性能优化

- ✅ 使用缓存减少数据库查询
- ✅ 使用连接池复用数据库连接
- ✅ 使用异步任务处理耗时操作
- ✅ 使用 CDN 加速静态资源
- ✅ 使用索引优化数据库查询

## 🔐 安全考虑

- ✅ 敏感配置使用环境变量
- ✅ 密码加密存储
- ✅ API 限流防止滥用
- ✅ 日志脱敏处理
- ✅ HTTPS 加密传输

## 🔄 版本历史

- **v1.0.0** (2024-01): 初始版本
- **v1.1.0** (2024-03): 添加性能监控
- **v1.2.0** (2024-06): 添加健康检查
- **v1.3.0** (2024-09): 添加 API 限流
