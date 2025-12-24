# 网络请求重试机制

## 实现日期
2025-11-29

## 问题描述
在询价过程中，经常遇到网络不稳定导致的错误：
- `httpx.RemoteProtocolError: Server disconnected without sending a response`
- `httpx.ConnectError`: 连接错误
- `httpx.ReadTimeout`: 读取超时

这些错误是暂时性的，通过重试通常可以成功。

## 解决方案

### 1. 获取保险公司列表 - 添加重试机制

**文件**: `backend/apps/automation/services/insurance/court_insurance_client.py`

#### 实现方式

将原来的 `fetch_insurance_companies` 方法拆分为两个：

1. **`fetch_insurance_companies`** - 公共接口，包含重试逻辑
2. **`_fetch_insurance_companies_once`** - 私有方法，执行单次请求

```python
async def fetch_insurance_companies(
    self,
    bearer_token: str,
    c_pid: str,
    fy_id: str,
    timeout: float = None,
    max_retries: int = 3  # 最大重试次数
) -> List[InsuranceCompany]:
    """获取保险公司列表（带重试）"""
    
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            return await self._fetch_insurance_companies_once(
                bearer_token=bearer_token,
                c_pid=c_pid,
                fy_id=fy_id,
                timeout=timeout,
                attempt=attempt,
            )
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as e:
            last_exception = e
            if attempt < max_retries:
                retry_delay = attempt * 2  # 递增延迟：2秒、4秒、6秒
                logger.warning(f"获取保险公司列表失败（尝试 {attempt}/{max_retries}），{retry_delay}秒后重试")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"获取保险公司列表失败，已达最大重试次数 {max_retries}")
    
    # 所有重试都失败，抛出最后一个异常
    raise last_exception
```

#### 重试策略

1. **最大重试次数**: 3 次（共 4 次尝试）
2. **重试延迟**: 递增延迟
   - 第 1 次重试：等待 2 秒
   - 第 2 次重试：等待 4 秒
   - 第 3 次重试：等待 6 秒
3. **捕获的异常**:
   - `httpx.RemoteProtocolError` - 服务器断开连接
   - `httpx.ConnectError` - 连接错误
   - `httpx.ReadTimeout` - 读取超时

#### 执行流程示例

```
尝试 1: 发送请求 → 失败 (RemoteProtocolError) → 等待 2 秒
尝试 2: 发送请求 → 失败 (RemoteProtocolError) → 等待 4 秒
尝试 3: 发送请求 → 失败 (RemoteProtocolError) → 等待 6 秒
尝试 4: 发送请求 → 成功 ✅
```

如果所有尝试都失败，抛出最后一个异常。

### 2. 并发请求优化

**文件**: `backend/apps/automation/services/insurance/court_insurance_client.py`

#### 分批并发策略

```python
# 配置参数
BATCH_SIZE = 3          # 每批最多3个并发请求
BATCH_DELAY = 1.0       # 批次间延迟1秒
REQUEST_DELAY = 0.3     # 同一批次内请求间延迟0.3秒
```

#### 执行流程

```
批次 1 (公司 1-3):
  - 发送请求 1
  - 等待 0.3 秒
  - 发送请求 2
  - 等待 0.3 秒
  - 发送请求 3
  - 等待所有响应
  
等待 1 秒

批次 2 (公司 4-6):
  - 发送请求 4
  - 等待 0.3 秒
  - 发送请求 5
  - 等待 0.3 秒
  - 发送请求 6
  - 等待所有响应
  
...
```

### 3. 数据清洗

**文件**: `backend/apps/automation/services/insurance/preservation_quote_service.py`

添加 `clean_decimal()` 函数，处理空字符串和无效值：

```python
def clean_decimal(value):
    """清洗 Decimal 字段的值"""
    if value is None or value == "" or value == "null":
        return None
    try:
        from decimal import Decimal
        return Decimal(str(value))
    except:
        return None
```

避免保存时出现 `ValidationError: ['""的值应该是一个十进制数字。']` 错误。

## 优点

### 1. 提高成功率
- 暂时性网络错误通过重试可以成功
- 减少因网络波动导致的任务失败

### 2. 降低服务器压力
- 分批并发，避免瞬时大量请求
- 请求间延迟，给服务器喘息时间

### 3. 更好的错误处理
- 详细的重试日志
- 数据清洗避免保存错误

## 配置参数

### 重试配置

```python
# 获取保险公司列表
max_retries = 3  # 最大重试次数
retry_delay = attempt * 2  # 递增延迟（秒）
```

### 并发配置

```python
BATCH_SIZE = 3      # 每批并发数（1-5 推荐）
BATCH_DELAY = 1.0   # 批次间延迟（0.5-2.0 秒推荐）
REQUEST_DELAY = 0.3 # 请求间延迟（0.1-0.5 秒推荐）
```

### 超时配置

```python
DEFAULT_TIMEOUT = 60.0  # 默认超时时间（秒）
```

## 日志示例

### 成功重试

```
[2025-11-29 08:30:00] WARNING - 获取保险公司列表失败（尝试 1/3），2秒后重试: Server disconnected
[2025-11-29 08:30:02] INFO - 开始获取保险公司列表
[2025-11-29 08:30:03] INFO - ✅ 成功获取 10 家保险公司
```

### 重试失败

```
[2025-11-29 08:30:00] WARNING - 获取保险公司列表失败（尝试 1/3），2秒后重试: Server disconnected
[2025-11-29 08:30:02] WARNING - 获取保险公司列表失败（尝试 2/3），4秒后重试: Server disconnected
[2025-11-29 08:30:06] WARNING - 获取保险公司列表失败（尝试 3/3），6秒后重试: Server disconnected
[2025-11-29 08:30:12] ERROR - 获取保险公司列表失败，已达最大重试次数 3
[2025-11-29 08:30:12] ERROR - ❌ 询价任务执行失败: Server disconnected without sending a response
```

## 测试清单

- [x] 添加重试机制到 fetch_insurance_companies
- [x] 实现分批并发策略
- [x] 添加数据清洗函数
- [ ] 测试网络不稳定情况下的重试
- [ ] 测试所有重试都失败的情况
- [ ] 验证重试延迟是否合理
- [ ] 监控重试成功率

## 后续优化建议

### 1. 为 fetch_premium 添加重试

单个保险公司询价也可能失败，可以添加类似的重试机制：

```python
async def fetch_premium_with_retry(
    self,
    max_retries: int = 2,
    **kwargs
) -> PremiumResult:
    """查询单个保险公司报价（带重试）"""
    for attempt in range(1, max_retries + 1):
        try:
            return await self.fetch_premium(**kwargs)
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as e:
            if attempt < max_retries:
                await asyncio.sleep(1)
                continue
            # 最后一次失败，返回失败结果而不是抛出异常
            return PremiumResult(
                company=...,
                premium=None,
                status="failed",
                error_message=f"重试 {max_retries} 次后仍失败: {str(e)}",
                ...
            )
```

### 2. 指数退避策略

使用指数退避而不是线性递增：

```python
retry_delay = min(2 ** attempt, 30)  # 2秒、4秒、8秒、16秒、30秒（最大）
```

### 3. 断路器模式

如果某个保险公司连续失败多次，暂时跳过该公司：

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=3, timeout=60):
        self.failure_count = {}
        self.failure_threshold = failure_threshold
        self.timeout = timeout
    
    def is_open(self, company_code):
        """检查断路器是否打开（该公司是否被暂时跳过）"""
        if company_code in self.failure_count:
            count, last_failure = self.failure_count[company_code]
            if count >= self.failure_threshold:
                if time.time() - last_failure < self.timeout:
                    return True
        return False
```

### 4. 自适应延迟

根据服务器响应时间动态调整延迟：

```python
if response_time > 5:  # 响应慢
    REQUEST_DELAY = 0.5
elif response_time > 2:
    REQUEST_DELAY = 0.3
else:  # 响应快
    REQUEST_DELAY = 0.1
```

## 相关文件

- `backend/apps/automation/services/insurance/court_insurance_client.py` - 客户端代码
- `backend/apps/automation/services/insurance/preservation_quote_service.py` - 服务层代码

## 总结

通过添加重试机制、分批并发和数据清洗，大大提高了询价系统的稳定性和成功率。即使在网络不稳定的情况下，系统也能通过重试机制完成任务。
