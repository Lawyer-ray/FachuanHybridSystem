# 请求对比分析

## 📋 您的脚本（正常工作）

### HTTP 请求

```
POST https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium?time=1732800682321&preserveAmount=3&institution=002&corpId=51
```

### 请求头

```
Accept: */*
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8
Bearer: eyJhbGciOiJIUzUxMiJ9...
Cache-Control: no-cache
Connection: keep-alive
Content-Type: application/json;charset=UTF-8
Origin: https://zxfw.court.gov.cn
Pragma: no-cache
Referer: https://zxfw.court.gov.cn/
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-site
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
sec-ch-ua: "Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "macOS"
```

### 请求体

```json
{
  "preserveAmount": "3",
  "institution": "002",
  "corpId": "51"
}
```

---

## 📋 我的实现（修复后）

### HTTP 请求

```
POST https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium?time=1732800682321&preserveAmount=3&institution=002&corpId=51
```

### 请求头

```
Accept: */*
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8
Bearer: eyJhbGciOiJIUzUxMiJ9...
Cache-Control: no-cache
Connection: keep-alive
Content-Type: application/json;charset=UTF-8
Origin: https://zxfw.court.gov.cn
Pragma: no-cache
Referer: https://zxfw.court.gov.cn/
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-site
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
sec-ch-ua: "Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "macOS"
```

### 请求体

```json
{
  "preserveAmount": "3",
  "institution": "002",
  "corpId": "51"
}
```


---

## ✅ 对比结果

| 项目 | 您的脚本 | 我的实现 | 状态 |
|------|----------|----------|------|
| HTTP 方法 | POST | POST | ✅ 一致 |
| URL | 相同 | 相同 | ✅ 一致 |
| 时间戳 | 毫秒级 | 毫秒级 | ✅ 一致 |
| Bearer Token | Bearer 字段 | Bearer 字段 | ✅ 一致 |
| 请求头 | 完整 | 完整 | ✅ 一致 |
| 请求体 | JSON | JSON | ✅ 一致 |
| 参数格式 | 字符串 | 字符串 | ✅ 一致 |

---

## 🔍 查看实际发送的请求

修复后的代码会在日志中打印完整的请求信息：

```
================================================================================
🔍 查询保险公司报价: 002
================================================================================
📍 URL: https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium
⏰ 时间戳: 1732800682321
📋 URL 参数:
   - time: 1732800682321
   - preserveAmount: 3
   - institution: 002
   - corpId: 51
📦 请求体:
   {'preserveAmount': '3', 'institution': '002', 'corpId': '51'}
🔑 Bearer Token (前20字符): eyJhbGciOiJIUzUxMiJ9...
================================================================================
```

---

## 🐛 HTTP 500 错误分析

您遇到的错误：

```json
{
  "code": 500,
  "message": "系统异常",
  "timestamp": 1764342682321,
  "data": null
}
```

### 可能的原因

1. **Token 过期**: Bearer Token 可能已经过期
2. **参数值错误**: `institution=002` 或 `corpId=51` 可能不是有效值
3. **服务器问题**: 后端服务暂时不可用
4. **时间戳问题**: 时间戳可能超出有效范围

### 验证步骤

#### 1. 检查 Token 是否有效

```bash
cd backend/apiSystem
python manage.py shell <<'EOF'
from apps.automation.models import CourtToken
from django.utils import timezone

tokens = CourtToken.objects.all()
for t in tokens:
    valid = not t.is_expired()
    print(f'{t.account}: Valid={valid}, Expires={t.expires_at}')
EOF
```

#### 2. 使用您的脚本测试相同参数

```python
# 使用您的脚本测试
CUSTOM_PARAMS = {
    "preserve_amount": 3,
    "institution": "002",
    "corp_id": "51",
    "bearer_token": "your_token_here"
}

result = asyncio.run(async_court_premium_request(**CUSTOM_PARAMS))
```

---

## 💡 下一步

1. **查看日志**: 检查 `backend/logs/api.log` 中的详细请求信息
2. **验证 Token**: 确认 Token 未过期且有效
3. **测试参数**: 使用您的脚本测试相同的参数组合
4. **对比请求**: 确认我的实现发送的请求与您的脚本完全一致

如果日志显示请求格式正确但仍然返回 500 错误，那么问题可能在于：
- Token 权限不足
- 参数值无效
- 服务器端问题

---

**创建日期**: 2025-11-28  
**状态**: 🔍 调试中
