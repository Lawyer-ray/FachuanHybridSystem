# ADR-004: 统一异常处理

## 状态

已接受 (2024-01-15)

## 背景

在重构前，异常处理混乱，存在以下问题：

1. **返回错误码**：Service 返回 None 或错误字典表示失败
2. **异常类型不统一**：使用 Python 内置异常或 Django 异常
3. **错误信息不结构化**：只有字符串消息，没有错误码和详细信息
4. **API 层处理复杂**：每个 API 都要处理各种异常

示例问题代码：

```python
# ❌ 返回错误码
def create_resource(self, data, user):
    if not user.has_perm('resources.add_resource'):
        return {"error": "无权限", "code": 403}
    
    if Resource.objects.filter(name=data.name).exists():
        return None
    
    return Resource.objects.create(...)

# ❌ API 层处理复杂
@router.post("/resources")
def create_resource(request, data):
    result = service.create_resource(data, request.auth)
    
    if result is None:
        return {"error": "创建失败"}, 400
    
    if isinstance(result, dict) and "error" in result:
        return result, result.get("code", 400)
    
    return result
```

这导致：
- API 层代码冗长，充满 if/else
- 错误处理不一致
- 难以调试
- 前端难以处理错误

## 决策

我们决定建立**统一的异常体系**：

### 原则

1. **Service 层抛出自定义异常**：不返回错误码
2. **所有异常继承自 BusinessException**：统一基类
3. **异常包含结构化信息**：message、code、errors
4. **API 层使用全局异常处理器**：自动转换为 HTTP 响应

### 异常体系

```python
BusinessException (基类)
├── ValidationException (400)
├── AuthenticationError (401)
├── PermissionDenied (403)
├── NotFoundError (404)
├── ConflictError (409)
├── RateLimitError (429)
└── ExternalServiceError (502)
```

### 实施方式

```python
# 1. 定义异常基类
class BusinessException(Exception):
    """业务异常基类"""
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code or self.__class__.__name__
        self.errors = errors or {}
        super().__init__(message)

# 2. Service 层抛出异常
class ResourceService:
    def create_resource(self, data, user):
        # ✅ 抛出 PermissionDenied
        if not user.has_perm('resources.add_resource'):
            raise PermissionDenied("无权限创建资源")
        
        # ✅ 抛出 ValidationException
        if Resource.objects.filter(name=data.name).exists():
            raise ValidationException(
                message="名称已存在",
                code="DUPLICATE_NAME",
                errors={"name": "该名称已被使用"}
            )
        
        return Resource.objects.create(...)

# 3. API 层使用全局异常处理器
@api.exception_handler(ValidationException)
def handle_validation_exception(request, exc):
    return api.create_response(
        request,
        {
            "error": exc.message,
            "code": exc.code,
            "errors": exc.errors
        },
        status=400
    )

# 4. API 层代码简化
@router.post("/resources")
def create_resource(request, data):
    # ✅ 不需要 try/except，异常会被全局处理器捕获
    service = ResourceService()
    resource = service.create_resource(data, request.auth)
    return ResourceSchema.from_orm(resource)
```

## 后果

### 正面影响

1. **API 层代码简化**
   - 不需要处理各种异常
   - 代码更清晰
   - 减少重复代码

2. **错误处理一致**
   - 所有错误都有统一格式
   - 前端易于处理
   - 易于调试

3. **结构化错误信息**
   - 包含错误消息、错误码、详细错误
   - 支持国际化
   - 支持字段级别错误

4. **提高可维护性**
   - 异常类型清晰
   - 易于添加新异常类型
   - 易于修改错误处理逻辑

5. **更好的日志**
   - 异常包含完整上下文
   - 易于追踪问题
   - 支持结构化日志

### 负面影响

1. **需要定义异常类**
   - 增加代码量
   - 需要维护异常类

2. **学习成本**
   - 开发者需要了解异常体系
   - 需要知道何时使用哪个异常

3. **性能开销**
   - 抛出异常有性能开销
   - 但对于错误场景可以接受

### 风险

1. **异常滥用**：将异常用于正常流程控制
   - **缓解措施**：代码审查，明确异常使用场景

2. **异常类型过多**：定义太多细粒度的异常类
   - **缓解措施**：只定义必要的异常类型

3. **忘记处理异常**：某些异常没有对应的处理器
   - **缓解措施**：添加通用异常处理器

## 替代方案

### 方案 1: 返回 Result 对象

使用 Result 对象封装成功和失败。

**优点**：
- 显式表示成功/失败
- 不使用异常
- 类型安全

**缺点**：
- 需要定义 Result 类
- 调用方需要检查 Result
- 代码冗长

**为什么不选择**：
- Python 社区更倾向使用异常
- Result 模式在 Python 中不常见
- 增加代码复杂度

### 方案 2: 使用 Django 内置异常

使用 Django 的 `ValidationError`、`PermissionDenied` 等。

**优点**：
- 不需要自定义异常
- Django 原生支持

**缺点**：
- 异常类型有限
- 不支持结构化错误信息
- 难以扩展

**为什么不选择**：
- 无法满足业务需求
- 缺少错误码
- 缺少结构化错误信息

### 方案 3: HTTP 异常

直接抛出 HTTP 异常（如 `HTTPException`）。

**优点**：
- 直接对应 HTTP 状态码
- 实现简单

**缺点**：
- Service 层包含 HTTP 概念
- 违反分层原则
- 难以测试

**为什么不选择**：
- Service 层不应该知道 HTTP
- 降低代码可测试性
- 违反架构原则

## 实施

### 已完成

1. ✅ 在 `apps/core/exceptions.py` 定义异常体系
2. ✅ 实现 BusinessException 基类
3. ✅ 定义所有具体异常类
4. ✅ 在 `apiSystem/api.py` 配置全局异常处理器
5. ✅ 重构所有 Service，使用自定义异常
6. ✅ 更新 API 层，移除异常处理代码
7. ✅ 编写测试，验证异常处理
8. ✅ 更新文档

### 异常类型列表

| 异常类型 | HTTP 状态码 | 使用场景 |
|---------|-----------|---------|
| ValidationException | 400 | 数据验证失败 |
| AuthenticationError | 401 | 认证失败 |
| PermissionDenied | 403 | 权限不足 |
| NotFoundError | 404 | 资源不存在 |
| ConflictError | 409 | 资源冲突 |
| RateLimitError | 429 | 频率限制 |
| ExternalServiceError | 502 | 外部服务错误 |
| BusinessException | 400 | 其他业务错误 |

### 响应格式

所有错误响应都遵循统一格式：

```json
{
  "error": "错误消息",
  "code": "ERROR_CODE",
  "errors": {
    "field1": "字段错误详情",
    "field2": "字段错误详情"
  }
}
```

### 示例代码

完整示例请参考：
- `apps/core/exceptions.py` - 异常定义
- `apiSystem/api.py` - 全局异常处理器
- `apps/cases/services/case_service.py` - 使用异常
- `apps/core/tests/test_exceptions.py` - 异常测试

## 参考资料

- [Python Exceptions Best Practices](https://docs.python.org/3/tutorial/errors.html)
- [REST API Error Handling](https://www.rfc-editor.org/rfc/rfc7807)
- [Django Exception Handling](https://docs.djangoproject.com/en/stable/ref/exceptions/)
- 项目规范文档：`.kiro/steering/django-python-expert.md`

## 更新历史

- 2024-01-15: 初始版本，决策已接受
- 2024-01-20: 完成异常体系实现
- 2024-01-25: 完成所有模块重构
