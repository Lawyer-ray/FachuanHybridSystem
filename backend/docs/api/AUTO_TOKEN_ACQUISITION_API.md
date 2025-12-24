# 自动Token获取功能 API 文档

## 概述

自动Token获取功能为财产保险询价服务提供了无缝的Token管理能力。当系统检测到Token无效时，会自动触发法院一张网登录流程，获取新Token后继续执行业务操作，无需人工干预。

## 核心接口

### IAutoTokenAcquisitionService

自动Token获取服务的核心接口，提供Token自动获取功能。

```python
from apps.core.interfaces import IAutoTokenAcquisitionService

class IAutoTokenAcquisitionService(Protocol):
    async def acquire_token_if_needed(
        self, 
        site_name: str, 
        credential_id: Optional[int] = None
    ) -> str:
        """
        如果需要则自动获取token
        
        Args:
            site_name: 网站名称（如 'court_zxfw'）
            credential_id: 指定的凭证ID（可选，None则自动选择最优账号）
            
        Returns:
            有效的token字符串
            
        Raises:
            AutoTokenAcquisitionError: Token获取失败
            ValidationException: 参数验证失败
            NoAvailableAccountError: 无可用账号
            TokenAcquisitionTimeoutError: 获取超时
        """
```

### IAccountSelectionStrategy

账号选择策略接口，用于选择最优的登录账号。

```python
from apps.core.interfaces import IAccountSelectionStrategy

class IAccountSelectionStrategy(Protocol):
    async def select_account(
        self, 
        site_name: str, 
        exclude_accounts: List[str] = None
    ) -> Optional[AccountCredentialDTO]:
        """
        选择用于登录的账号
        
        Args:
            site_name: 网站名称
            exclude_accounts: 排除的账号列表（可选）
            
        Returns:
            选中的账号凭证DTO，如果无可用账号则返回None
        """
```

### IAutoLoginService

自动登录服务接口，执行具体的登录操作。

```python
from apps.core.interfaces import IAutoLoginService

class IAutoLoginService(Protocol):
    async def login_and_get_token(
        self, 
        credential: AccountCredentialDTO
    ) -> str:
        """
        执行自动登录并返回token
        
        Args:
            credential: 账号凭证DTO
            
        Returns:
            获取到的token字符串
            
        Raises:
            LoginFailedError: 登录失败
            TokenAcquisitionTimeoutError: 登录超时
        """
```

## 数据传输对象 (DTO)

### AccountCredentialDTO

账号凭证数据传输对象，用于跨模块传递账号信息。

```python
@dataclass
class AccountCredentialDTO:
    """账号凭证数据传输对象"""
    id: int
    lawyer_id: int
    site_name: str
    url: Optional[str]
    account: str
    password: str
    last_login_success_at: Optional[str] = None
    login_success_count: int = 0
    login_failure_count: int = 0
    is_preferred: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_model(cls, credential) -> "AccountCredentialDTO":
        """从 AccountCredential Model 转换为 DTO"""
```

### LoginAttemptResult

登录尝试结果DTO，记录单次登录尝试的详细信息。

```python
@dataclass
class LoginAttemptResult:
    """登录尝试结果DTO"""
    success: bool
    token: Optional[str]
    account: str
    error_message: Optional[str]
    attempt_duration: float
    retry_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
```

### TokenAcquisitionResult

Token获取结果DTO，记录完整的Token获取流程结果。

```python
@dataclass
class TokenAcquisitionResult:
    """Token获取结果DTO"""
    success: bool
    token: Optional[str]
    acquisition_method: str  # "existing", "auto_login"
    total_duration: float
    login_attempts: List[LoginAttemptResult]
    error_details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
```

## 异常处理

### 异常层次结构

```python
BusinessException
├── ExternalServiceError
    ├── AutoTokenAcquisitionError          # 自动Token获取基础异常
        ├── LoginFailedError               # 登录失败异常
        ├── NoAvailableAccountError        # 无可用账号异常
        └── TokenAcquisitionTimeoutError   # Token获取超时异常
```

### 异常详情

#### AutoTokenAcquisitionError

自动Token获取基础异常，HTTP状态码：502

```python
class AutoTokenAcquisitionError(ExternalServiceError):
    """
    自动Token获取基础异常
    
    使用场景：
    - 自动Token获取流程中的各种错误
    - 作为其他Token获取异常的基类
    """
```

#### LoginFailedError

登录失败异常，HTTP状态码：502

```python
class LoginFailedError(AutoTokenAcquisitionError):
    """
    登录失败异常
    
    使用场景：
    - 账号密码错误
    - 验证码识别失败
    - 登录流程异常
    
    属性：
    - attempts: List[LoginAttemptResult] - 登录尝试记录
    """
```

#### NoAvailableAccountError

无可用账号异常，HTTP状态码：502

```python
class NoAvailableAccountError(AutoTokenAcquisitionError):
    """
    无可用账号异常
    
    使用场景：
    - 没有配置账号凭证
    - 所有账号都已失效
    - 所有账号都在黑名单中
    """
```

#### TokenAcquisitionTimeoutError

Token获取超时异常，HTTP状态码：502

```python
class TokenAcquisitionTimeoutError(AutoTokenAcquisitionError):
    """
    Token获取超时异常
    
    使用场景：
    - 登录过程超时
    - Token获取流程超时
    """
```

## ServiceLocator 使用

### 获取服务实例

```python
from apps.core.interfaces import ServiceLocator

# 获取自动Token获取服务
auto_token_service = ServiceLocator.get_auto_token_acquisition_service()

# 获取账号选择策略服务
account_strategy = ServiceLocator.get_account_selection_strategy()

# 获取自动登录服务
auto_login_service = ServiceLocator.get_auto_login_service()
```

### 测试时注入Mock

```python
from unittest.mock import Mock
from apps.core.interfaces import ServiceLocator, IAutoTokenAcquisitionService

# 创建Mock服务
mock_service = Mock(spec=IAutoTokenAcquisitionService)
mock_service.acquire_token_if_needed.return_value = "mock_token_12345"

# 注入Mock服务
ServiceLocator.register("auto_token_acquisition_service", mock_service)

# 清理（测试后）
ServiceLocator.clear()
```

## 使用示例

### 基本使用

```python
from apps.core.interfaces import ServiceLocator

async def example_basic_usage():
    """基本使用示例"""
    # 获取服务实例
    service = ServiceLocator.get_auto_token_acquisition_service()
    
    try:
        # 自动获取Token（自动选择账号）
        token = await service.acquire_token_if_needed("court_zxfw")
        print(f"获取到Token: {token}")
        
        # 使用指定凭证ID获取Token
        token = await service.acquire_token_if_needed("court_zxfw", credential_id=1)
        print(f"使用指定凭证获取Token: {token}")
        
    except NoAvailableAccountError:
        print("错误：无可用账号，请检查账号配置")
    except LoginFailedError as e:
        print(f"登录失败：{e.message}")
        print(f"尝试次数：{len(e.attempts)}")
    except TokenAcquisitionTimeoutError:
        print("错误：Token获取超时")
    except AutoTokenAcquisitionError as e:
        print(f"Token获取失败：{e.message}")
```

### 在Service层集成

```python
from apps.core.interfaces import ServiceLocator, IAutoTokenAcquisitionService

class MyBusinessService:
    """业务服务示例"""
    
    def __init__(self, auto_token_service: Optional[IAutoTokenAcquisitionService] = None):
        self._auto_token_service = auto_token_service
    
    @property
    def auto_token_service(self) -> IAutoTokenAcquisitionService:
        """获取自动Token服务（延迟加载）"""
        if self._auto_token_service is None:
            self._auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
        return self._auto_token_service
    
    async def execute_business_logic(self, site_name: str, credential_id: Optional[int] = None):
        """执行业务逻辑"""
        try:
            # 确保有有效Token
            token = await self.auto_token_service.acquire_token_if_needed(
                site_name, credential_id
            )
            
            # 使用Token执行业务操作
            result = await self._do_business_operation(token)
            return result
            
        except AutoTokenAcquisitionError as e:
            logger.error(f"Token获取失败: {e}")
            raise
    
    async def _do_business_operation(self, token: str):
        """具体的业务操作"""
        # 实现具体业务逻辑
        pass
```

### API层集成（工厂函数模式）

```python
from apps.core.interfaces import ServiceLocator

def _get_my_service() -> MyBusinessService:
    """
    工厂函数：创建业务服务实例并注入依赖
    
    Returns:
        MyBusinessService 实例，已集成自动Token获取功能
    """
    # 通过ServiceLocator获取依赖
    auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
    
    # 创建服务实例并注入依赖
    return MyBusinessService(auto_token_service=auto_token_service)

@router.post("/my-endpoint")
async def my_endpoint(request: HttpRequest, data: MyRequestSchema):
    """API端点示例"""
    # 使用工厂函数创建服务
    service = _get_my_service()
    
    # 执行业务逻辑（自动处理Token）
    result = await service.execute_business_logic("court_zxfw")
    
    return {"success": True, "data": result}
```

## 性能监控

### 获取性能指标

```python
from apps.automation.services.token.performance_monitor import performance_monitor

# 获取实时性能指标
metrics = performance_monitor.get_metrics()
print(f"总获取次数: {metrics.total_acquisitions}")
print(f"成功率: {metrics.success_rate:.2f}%")
print(f"平均耗时: {metrics.avg_duration:.2f}秒")

# 获取统计报告
stats = performance_monitor.get_statistics()
print(f"今日成功次数: {stats.today_success_count}")
print(f"本周成功率: {stats.week_success_rate:.2f}%")
```

### 缓存管理

```python
from apps.automation.services.token.cache_manager import cache_manager

# 手动缓存Token
cache_manager.cache_token("court_zxfw", "test_account", "token_12345")

# 获取缓存的Token
token = cache_manager.get_cached_token("court_zxfw", "test_account")

# 清除缓存
cache_manager.clear_cache("court_zxfw")

# 预热缓存
cache_manager.warm_up_cache("court_zxfw")
```

## 配置说明

### 并发控制配置

```python
from apps.automation.services.token.concurrency_optimizer import ConcurrencyConfig

# 自定义并发配置
config = ConcurrencyConfig(
    max_concurrent_acquisitions=3,      # 最大并发获取数
    max_concurrent_per_site=2,          # 每个站点最大并发数
    max_concurrent_per_account=1,       # 每个账号最大并发数
    acquisition_timeout=300.0           # 获取超时时间（秒）
)
```

### 环境要求

- Django 5.2+
- Redis（用于缓存）
- 已配置的账号凭证（AccountCredential）
- 可用的浏览器自动化环境（Playwright）

## 错误处理最佳实践

### 1. 分层错误处理

```python
async def handle_token_acquisition():
    """错误处理示例"""
    try:
        token = await service.acquire_token_if_needed("court_zxfw")
        return token
    except NoAvailableAccountError:
        # 无可用账号 - 需要管理员配置账号
        logger.error("无可用账号，请检查账号配置")
        raise BusinessException("系统配置错误，请联系管理员")
    except LoginFailedError as e:
        # 登录失败 - 可能是账号问题或网络问题
        logger.error(f"登录失败: {e.message}, 尝试次数: {len(e.attempts)}")
        raise BusinessException("登录失败，请稍后重试")
    except TokenAcquisitionTimeoutError:
        # 超时 - 网络或系统负载问题
        logger.error("Token获取超时")
        raise BusinessException("系统繁忙，请稍后重试")
    except AutoTokenAcquisitionError as e:
        # 其他Token获取错误
        logger.error(f"Token获取失败: {e.message}")
        raise BusinessException("Token获取失败，请稍后重试")
```

### 2. 重试机制

```python
import asyncio
from typing import Optional

async def acquire_token_with_retry(
    service: IAutoTokenAcquisitionService,
    site_name: str,
    credential_id: Optional[int] = None,
    max_retries: int = 3,
    retry_delay: float = 5.0
) -> str:
    """带重试的Token获取"""
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await service.acquire_token_if_needed(site_name, credential_id)
        except (LoginFailedError, TokenAcquisitionTimeoutError) as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(f"Token获取失败，{retry_delay}秒后重试 (尝试 {attempt + 1}/{max_retries + 1})")
                await asyncio.sleep(retry_delay)
                retry_delay *= 1.5  # 指数退避
            else:
                logger.error(f"Token获取最终失败，已重试{max_retries}次")
        except (NoAvailableAccountError, AutoTokenAcquisitionError):
            # 这些错误不适合重试
            raise
    
    # 重试耗尽，抛出最后一个异常
    raise last_exception
```

## 监控和日志

### 结构化日志

系统提供详细的结构化日志记录：

```python
# 开始Token获取流程
logger.info("开始Token获取流程", extra={
    "acquisition_id": "court_zxfw_auto_1640995200",
    "site_name": "court_zxfw",
    "credential_id": None,
    "trigger_reason": "token_needed"
})

# 账号选择
logger.info("选择登录账号", extra={
    "acquisition_id": "court_zxfw_auto_1640995200",
    "selected_account": "test@example.com",
    "selection_reason": "most_recent_success"
})

# 登录成功
logger.info("登录成功", extra={
    "acquisition_id": "court_zxfw_auto_1640995200",
    "account": "test@example.com",
    "login_duration": 15.2,
    "token_length": 32
})
```

### 性能指标

关键性能指标包括：

- **总获取次数**: 累计Token获取请求数
- **成功率**: 成功获取Token的比例
- **平均耗时**: Token获取的平均时间
- **并发数**: 当前并发获取的任务数
- **缓存命中率**: 缓存Token的命中比例

## 故障排除

### 常见问题及解决方案

1. **NoAvailableAccountError**
   - 检查是否配置了账号凭证
   - 验证账号凭证是否有效
   - 检查账号是否在黑名单中

2. **LoginFailedError**
   - 检查账号密码是否正确
   - 验证验证码识别服务是否正常
   - 检查网络连接状态

3. **TokenAcquisitionTimeoutError**
   - 检查网络延迟
   - 调整超时配置
   - 检查系统负载

4. **缓存问题**
   - 检查Redis服务状态
   - 验证缓存配置
   - 清理过期缓存

### 调试工具

```python
# 启用详细日志
import logging
logging.getLogger('apps.automation.services.token').setLevel(logging.DEBUG)

# 检查服务状态
from apps.automation.services.token.performance_monitor import performance_monitor
health = performance_monitor.get_health_status()
print(f"系统健康状态: {health.status}")

# 检查缓存状态
from apps.automation.services.token.cache_manager import cache_manager
cache_stats = cache_manager.get_cache_stats()
print(f"缓存命中率: {cache_stats.hit_rate:.2f}%")
```

## 总结

自动Token获取功能提供了完整的Token管理解决方案，具有以下特点：

1. **自动化**: 无需人工干预的Token获取和管理
2. **可靠性**: 完善的错误处理和重试机制
3. **高性能**: Redis缓存和并发优化
4. **可监控**: 详细的日志记录和性能指标
5. **易集成**: 清晰的接口设计和依赖注入模式
6. **可测试**: 支持Mock注入的测试友好设计

通过遵循本文档的指导，开发者可以轻松地将自动Token获取功能集成到自己的服务中，提升系统的自动化水平和用户体验。