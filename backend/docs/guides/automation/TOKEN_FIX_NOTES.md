# Token 捕获修复说明

## 问题

登录成功后，Token 没有被捕获和保存到数据库。

## 原因

使用 `page.route()` 路由拦截器在某些情况下不够可靠，可能无法正确捕获响应。

## 解决方案

改用 `page.on("response")` 事件监听器，这是 Playwright 推荐的监听响应的方式。

## 修改内容

### 修改文件
`backend/apps/automation/services/scraper/sites/court_zxfw.py`

### 修改前（使用 route 拦截器）
```python
def handle_login_response(route):
    response = route.fetch()
    if "login" in route.request.url.lower():
        response_body = response.json()
        # 提取 token...
    route.fulfill(response=response)

self.page.route("**/*", handle_login_response)
```

### 修改后（使用 response 监听器）
```python
def handle_response(response):
    if "login" in response.url.lower() and response.status == 200:
        response_body = response.json()
        # 提取 token...

self.page.on("response", handle_response)
```

## 优势

1. **更可靠**: `on("response")` 是 Playwright 推荐的方式
2. **更简单**: 不需要 `route.fetch()` 和 `route.fulfill()`
3. **更高效**: 不会阻塞请求
4. **更稳定**: 不会因为拦截器错误导致页面卡住

## 测试步骤

1. **重启服务**
   ```bash
   cd backend
   make run
   ```

2. **访问测试页面**
   ```
   http://localhost:8000/admin/automation/testcourt/
   ```

3. **查看日志**
   打开新终端：
   ```bash
   cd backend
   tail -f logs/api.log | grep -E "(Token|token|响应)"
   ```

4. **执行测试登录**
   - 选择账号凭证
   - 点击"测试登录"
   - 等待登录完成

5. **确认日志输出**
   应该看到：
   ```
   ✅ 已设置响应监听器，准备捕获 Token
   📡 捕获到登录接口响应: https://.../api/v1/login
      状态码: 200
   📄 响应内容: {'code': 200, 'data': {'token': 'xxx...', ...}, ...}
   ✅ 从 data.token 捕获到 Token: eyJ0eXAiOiJKV1QiLCJ...
   💾 准备保存 Token: court_zxfw - your_account
      Token 长度: 200 字符
   ✅ Token 已成功保存到 Redis 和数据库
      网站: court_zxfw
      账号: your_account
      Token 预览: eyJ0eXAiOiJKV1QiLCJhbGciOiJIUz...
   ```

6. **检查 Admin 后台**
   访问：
   ```
   http://localhost:8000/admin/automation/courttoken/
   ```
   
   应该能看到刚才保存的 Token。

## 支持的响应格式

代码现在支持以下所有格式：

1. **data.token**（你的情况）
   ```json
   {
     "code": 200,
     "data": {
       "token": "xxx..."
     }
   }
   ```

2. **data.access_token**
   ```json
   {
     "data": {
       "access_token": "xxx..."
     }
   }
   ```

3. **result.token**
   ```json
   {
     "result": {
       "token": "xxx..."
     }
   }
   ```

4. **直接 token**
   ```json
   {
     "token": "xxx..."
   }
   ```

## 如果还是不工作

1. **检查日志**
   ```bash
   tail -f backend/logs/api.log
   ```
   
   查找：
   - "✅ 已设置响应监听器" - 确认监听器已设置
   - "📡 捕获到登录接口响应" - 确认捕获到响应
   - "📄 响应内容" - 查看完整响应
   - "✅ 从 data.token 捕获到 Token" - 确认提取成功

2. **运行调试脚本**
   ```bash
   make debug-token
   ```

3. **手动测试 TokenService**
   ```bash
   python apiSystem/manage.py shell
   ```
   
   ```python
   from apps.automation.services.scraper.core.token_service import TokenService
   
   ts = TokenService()
   ts.save_token("court_zxfw", "test", "test_token_123")
   print(ts.get_token("court_zxfw", "test"))
   ```

## 相关文档

- [Token 故障排查指南](./TOKEN_TROUBLESHOOTING.md)
- [Token 服务使用指南](./TOKEN_SERVICE_GUIDE.md)
- [Token Admin 管理指南](./TOKEN_ADMIN_GUIDE.md)

---

**修复时间**: 2024-01-XX  
**修复方式**: 改用 `page.on("response")` 事件监听器
