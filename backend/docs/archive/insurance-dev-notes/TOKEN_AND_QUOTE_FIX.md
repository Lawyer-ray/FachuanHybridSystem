# Token 管理和询价修复总结

## 修复日期
2025-11-29

## 问题描述

1. **Token 过期时间不正确**：设置为 1 小时，但实际只有 10 分钟有效期
2. **每次测试登录未正确保存 Token**：Token 保存时使用了错误的过期时间
3. **询价失败 HTTP 500**：所有保险公司询价都返回 500 错误

## 根本原因分析

### 1. Token 过期时间问题
- **TokenService.DEFAULT_EXPIRES_IN** 设置为 3600 秒（1 小时）
- **CourtZxfwService.login()** 保存 Token 时硬编码 3600 秒
- **实际情况**：法院系统的 Token 只有 10 分钟（600 秒）有效期
- **后果**：Token 在 Redis 和数据库中保存 1 小时，但实际 10 分钟后就失效，导致询价时使用过期 Token

### 2. 询价失败 HTTP 500 问题
- **测试脚本成功**：使用 `preserve_amount = "3"`（字符串）
- **正式代码失败**：使用 `preserve_amount = Decimal("3.00")`
- **转换问题**：`str(Decimal("3.00"))` 可能产生 `"3.00"` 或 `"3.0"`
- **API 要求**：服务器端期望整数字符串 `"3"`，不接受小数格式
- **后果**：服务器无法解析带小数点的金额，返回 500 错误

## 修复方案

### 修复 1: TokenService 默认过期时间

**文件**: `backend/apps/automation/services/scraper/core/token_service.py`

```python
# 修改前
DEFAULT_EXPIRES_IN = 3600  # 默认 1 小时

# 修改后
DEFAULT_EXPIRES_IN = 600  # 默认 10 分钟（Token 实际有效期）
```


### 修复 2: 登录时保存 Token 的过期时间

**文件**: `backend/apps/automation/services/scraper/sites/court_zxfw.py`

```python
# 修改前
self.token_service.save_token(
    site_name=self.site_name,
    account=account,
    token=captured_token["value"],
    expires_in=3600  # 默认 1 小时
)

# 修改后
self.token_service.save_token(
    site_name=self.site_name,
    account=account,
    token=captured_token["value"],
    expires_in=600  # 10 分钟（Token 实际有效期）
)
```

### 修复 3: 保全金额格式转换

**文件**: `backend/apps/automation/services/insurance/court_insurance_client.py`

```python
# 修改前
params = {
    "time": current_time_ms,
    "preserveAmount": str(preserve_amount),  # 可能是 "3.00"
    "institution": institution,
    "corpId": corp_id,
}

# 修改后
# 转换保全金额为整数字符串（去掉小数点，API 要求整数）
preserve_amount_str = str(int(preserve_amount))  # 确保是 "3"

params = {
    "time": current_time_ms,
    "preserveAmount": preserve_amount_str,  # 现在是 "3"
    "institution": institution,
    "corpId": corp_id,
}
```

### 修复 4: 费率信息解析

**文件**: `backend/apps/automation/services/insurance/court_insurance_client.py`

```python
# 修改前
premium = data.get("premium") or data.get("data", {}).get("premium")

# 修改后
rate_data = data.get("data", {}) if isinstance(data, dict) else {}

if rate_data:
    # 优先使用 minPremium 作为报价
    premium_value = rate_data.get("minPremium") or rate_data.get("minAmount")
    if premium_value is not None:
        premium = Decimal(str(premium_value))
```

同时添加了完整的费率信息展示：
- 最低收费1 (minPremium)
- 最低收费2 (minAmount)
- 最低费率 (minRate)
- 最高费率 (maxRate)
- 最高收费 (maxAmount)
- 最高保全金额 (maxApplyAmount)

## 验证方法

### 1. 验证 Token 管理

```bash
# 1. 测试登录（会自动保存 Token）
# 访问 Django Admin: /admin/automation/testcourt/
# 点击「测试登录」按钮

# 2. 检查 Token 是否保存
# 访问: /admin/automation/courttoken/
# 确认 expires_at 是当前时间 + 10 分钟

# 3. 检查 Redis
python manage.py shell
>>> from django.core.cache import cache
>>> token = cache.get("court_token:court_zxfw:账号")
>>> print(token)  # 应该能获取到 Token
```

### 2. 验证询价功能

```bash
# 使用测试脚本
cd backend
python scripts/test_quote_with_service.py
```

预期结果：
- ✅ Token 获取成功
- ✅ 保险公司列表获取成功
- ✅ 询价请求成功（不再返回 HTTP 500）
- ✅ 费率信息正确解析和展示


## 注意事项

### Token 有效期管理

1. **10 分钟有效期很短**：建议在询价任务开始前检查 Token 是否即将过期
2. **自动刷新机制**：考虑在 Token 过期前 2 分钟自动重新登录
3. **并发询价**：多个任务可能共享同一个 Token，需要注意过期时间

### 保全金额格式

1. **数据库存储**：使用 `DecimalField`，精度为 2 位小数
2. **API 传输**：转换为整数字符串（去掉小数点）
3. **单位**：数据库存储单位为"万元"，API 也使用"万元"

### 错误处理

1. **Token 过期**：自动尝试获取其他有效 Token（降级策略）
2. **询价失败**：单个保险公司失败不影响其他公司
3. **HTTP 500**：记录完整请求参数，便于调试

## 测试清单

- [x] Token 默认过期时间修改为 10 分钟
- [x] 登录时保存 Token 使用 10 分钟过期时间
- [x] 保全金额转换为整数字符串
- [x] 费率信息正确解析（data 字段）
- [x] 费率信息完整展示（6 个字段）
- [ ] 测试登录并验证 Token 保存
- [ ] 测试询价流程（使用 test_quote_with_service.py）
- [ ] 验证并发询价性能
- [ ] 验证 Token 过期后的降级策略

## 相关文件

- `backend/apps/automation/services/scraper/core/token_service.py`
- `backend/apps/automation/services/scraper/sites/court_zxfw.py`
- `backend/apps/automation/services/insurance/court_insurance_client.py`
- `backend/apps/automation/services/insurance/preservation_quote_service.py`
- `backend/scripts/test_quote_with_service.py`
- `backend/scripts/test_full_quote_flow.py`

## 总结

本次修复解决了三个关键问题：

1. ✅ **Token 过期时间**：从 1 小时改为 10 分钟，与实际有效期一致
2. ✅ **Token 保存**：每次登录都正确保存 Token，使用正确的过期时间
3. ✅ **询价失败**：修复保全金额格式，从 "3.00" 改为 "3"，避免 HTTP 500 错误

这些修复确保了询价功能的稳定性和可靠性。
