# API 调用修复说明

## 🐛 问题描述

保险询价 API 调用失败，无法获取报价数据。

## 🔍 根本原因

通过对比用户的正常工作脚本，发现了以下关键差异：

### 1. **HTTP 方法错误** ⚠️⚠️⚠️
- **错误**: 使用 `GET` 请求
- **正确**: 使用 `POST` 请求

### 2. **缺少时间戳参数** ⚠️⚠️⚠️
- **错误**: URL 参数中没有 `time` 字段
- **正确**: 需要毫秒级时间戳 `time=1732800000000`

### 3. **请求头格式错误** ⚠️⚠️
- **错误**: `"Authorization": f"Bearer {token}"`
- **正确**: `"Bearer": token`

### 4. **缺少请求体** ⚠️⚠️
- **错误**: 只有 URL 参数，没有请求体
- **正确**: 需要 JSON 请求体

### 5. **缺少必要的请求头** ⚠️
- 缺少 `Origin`, `Referer`, `User-Agent` 等字段

## ✅ 修复内容

### 修复前的代码

```python
async def fetch_premium(self, bearer_token, preserve_amount, institution, corp_id):
    headers = {
        "Authorization": f"Bearer {bearer_token}",  # ❌ 错误
        "Content-Type": "application/json",
    }
    
    params = {
        "preserveAmount": str(preserve_amount),
        "institution": institution,
        "corpId": corp_id,
        # ❌ 缺少时间戳
    }
    
    # ❌ 使用 GET 请求
    response = await self._client.get(
        self.PREMIUM_QUERY_URL,
        headers=headers,
        params=params,
        # ❌ 没有请求体
    )
```

### 修复后的代码

```python
async def fetch_premium(self, bearer_token, preserve_amount, institution, corp_id):
    import time
    
    # ✅ 生成毫秒级时间戳
    current_time_ms = str(int(time.time() * 1000))
    
    # ✅ 完整的请求头
    headers = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Bearer": bearer_token,  # ✅ 直接使用 Bearer 字段
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://zxfw.court.gov.cn",
        "Pragma": "no-cache",
        "Referer": "https://zxfw.court.gov.cn/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }
    
    # ✅ URL 参数（包含时间戳）
    params = {
        "time": current_time_ms,  # ✅ 添加时间戳
        "preserveAmount": str(preserve_amount),
        "institution": institution,
        "corpId": corp_id,
    }
    
    # ✅ 请求体数据
    request_body = {
        "preserveAmount": str(preserve_amount),
        "institution": institution,
        "corpId": corp_id,
    }
    
    # ✅ 使用 POST 请求
    response = await self._client.post(
        self.PREMIUM_QUERY_URL,
        headers=headers,
        params=params,
        json=request_body,  # ✅ 添加请求体
        timeout=timeout,
    )
```

## 📊 修复对比表

| 项目 | 修复前 | 修复后 | 重要性 |
|------|--------|--------|--------|
| HTTP 方法 | GET | POST | ⚠️⚠️⚠️ |
| 时间戳 | 无 | 毫秒级时间戳 | ⚠️⚠️⚠️ |
| Bearer Token | Authorization 字段 | Bearer 字段 | ⚠️⚠️ |
| 请求体 | 无 | JSON 数据 | ⚠️⚠️ |
| 请求头 | 简化版 | 完整版 | ⚠️ |

## 🧪 测试验证

### 测试脚本

```python
import asyncio
from decimal import Decimal
from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
from apps.automation.services.scraper.core.token_service import TokenService

async def test_api_fix():
    token_service = TokenService()
    client = CourtInsuranceClient(token_service)
    
    # 测试参数
    bearer_token = "your_token_here"
    preserve_amount = Decimal("6652")
    institution = "FUDE"
    corp_id = "2550"
    
    # 调用 API
    result = await client.fetch_premium(
        bearer_token=bearer_token,
        preserve_amount=preserve_amount,
        institution=institution,
        corp_id=corp_id,
    )
    
    print(f"状态: {result.status}")
    print(f"报价: {result.premium}")
    print(f"错误: {result.error_message}")
    
    await client.close()

# 运行测试
asyncio.run(test_api_fix())
```

### 预期结果

```
状态: success
报价: 123.45
错误: None
```

## 🔍 API 规范

### 端点

```
POST https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium
```

### URL 参数

```
?time=1732800000000&preserveAmount=6652&institution=FUDE&corpId=2550
```

### 请求头（必需）

```
Bearer: eyJhbGciOiJIUzUxMiJ9...
Content-Type: application/json;charset=UTF-8
Origin: https://zxfw.court.gov.cn
Referer: https://zxfw.court.gov.cn/
```

### 请求体

```json
{
  "preserveAmount": "6652",
  "institution": "FUDE",
  "corpId": "2550"
}
```

### 响应示例

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "premium": 123.45
  }
}
```

## 💡 经验教训

1. **不要假设 API 规范**: 即使看起来像 RESTful API，也要验证实际的请求格式
2. **时间戳很重要**: 某些 API 使用时间戳进行签名验证或防重放攻击
3. **请求头字段名称**: `Bearer` vs `Authorization` 可能导致认证失败
4. **HTTP 方法**: GET vs POST 会导致完全不同的行为
5. **参考实际工作的代码**: 用户提供的工作脚本是最可靠的参考

## 🚀 部署建议

### 1. 更新代码

```bash
git pull origin main
```

### 2. 重启服务

```bash
# 重启 Django 应用
sudo systemctl restart gunicorn

# 重启 Django Q
sudo systemctl restart django-q
```

### 3. 验证修复

```bash
cd backend/apiSystem
python manage.py shell <<'EOF'
import asyncio
from decimal import Decimal
from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
from apps.automation.services.scraper.core.token_service import TokenService

async def test():
    token_service = TokenService()
    client = CourtInsuranceClient(token_service)
    
    # 使用实际的 Token 测试
    token = token_service.get_token(site_name="court_zxfw", account="your_account")
    if not token:
        print("❌ Token 不存在")
        return
    
    result = await client.fetch_premium(
        bearer_token=token,
        preserve_amount=Decimal("6652"),
        institution="FUDE",
        corp_id="2550",
    )
    
    print(f"✅ 测试结果: {result.status}")
    await client.close()

asyncio.run(test())
EOF
```

## 📝 相关文件

- `backend/apps/automation/services/insurance/court_insurance_client.py` - 修复的文件
- `backend/apps/automation/services/insurance/preservation_quote_service.py` - 调用方

## 🎉 总结

本次修复解决了 API 调用失败的问题：

1. ✅ **HTTP 方法**: GET → POST
2. ✅ **时间戳**: 添加毫秒级时间戳
3. ✅ **请求头**: Bearer 字段 + 完整请求头
4. ✅ **请求体**: 添加 JSON 请求体
5. ✅ **兼容性**: 与用户的工作脚本完全一致

现在 API 调用应该能够正常工作了！

---

**修复日期**: 2025-11-28  
**版本**: v2.2.0  
**状态**: ✅ 已修复
