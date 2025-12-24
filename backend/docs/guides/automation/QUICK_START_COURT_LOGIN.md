# 快速开始：测试法院"一张网"登录

## 1. 安装依赖

```bash
cd backend
pip install ddddocr
```

## 2. 准备账号密码

### 方式 1：通过 API 添加

启动后端服务：

```bash
make run
```

访问 Django Admin：http://127.0.0.1:8002/admin

添加账号凭证：
- 导航到：组织管理 → 账号密码
- 点击"添加账号密码"
- 填写信息：
  - 律师：选择一个律师
  - 网站名称：全国法院一张网
  - URL：https://zxfw.court.gov.cn
  - 账号：你的账号
  - 密码：你的密码
- 保存

### 方式 2：通过 API 添加

```bash
curl -X POST http://127.0.0.1:8002/api/v1/organization/credentials \
  -H "Content-Type: application/json" \
  -d '{
    "lawyer_id": 1,
    "site_name": "全国法院一张网",
    "url": "https://zxfw.court.gov.cn",
    "account": "your_account",
    "password": "your_password"
  }'
```

## 3. 运行测试

### 方式 1：使用 Makefile

```bash
cd backend
make test-court-login
```

### 方式 2：直接运行 Python

```bash
cd backend
python apps/automation/tests/test_court_zxfw_login.py
```

## 4. 观察结果

测试脚本会：

1. ✅ 从 API 获取账号密码
2. ✅ 启动浏览器（有头模式，可以看到操作过程）
3. ✅ 导航到登录页
4. ✅ 输入账号密码
5. ✅ 自动识别验证码
6. ✅ 点击登录
7. ✅ 检查登录结果
8. ✅ 保存调试信息

**调试文件位置：**
- 截图：`media/automation/screenshots/`
- 验证码图片：`media/automation/debug/`

## 5. 常见问题

### Q1: 提示"获取账号密码失败"

**原因：** 后端服务未启动或数据库中没有凭证记录

**解决：**
```bash
# 启动后端服务
cd backend
make run

# 在另一个终端运行测试
make test-court-login
```

### Q2: 提示"ddddocr 未安装"

**解决：**
```bash
pip install ddddocr
```

### Q3: 验证码识别失败

**原因：** ddddocr 识别率不是 100%

**解决：**
- 测试脚本会自动重试 5 次
- 查看验证码图片：`media/automation/debug/captcha_*.png`
- 如果多次失败，考虑使用付费 OCR 服务

### Q4: 浏览器启动失败

**原因：** Playwright 浏览器未安装

**解决：**
```bash
playwright install chromium
```

## 6. 下一步

登录成功后，可以：

1. **实现立案功能**：在 `CourtZxfwService.file_case()` 中添加逻辑
2. **实现查询功能**：在 `CourtZxfwService.query_case()` 中添加逻辑
3. **创建爬虫任务**：使用 `CourtFilingScraper` 调用登录服务

## 7. 代码示例

### 在你的代码中使用

```python
from playwright.sync_api import sync_playwright
from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

# 1. 启动浏览器
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    
    # 2. 创建服务
    service = CourtZxfwService(page, context)
    
    # 3. 登录
    result = service.login(
        account="your_account",
        password="your_password",
        max_captcha_retries=5,
        save_debug=True
    )
    
    # 4. 使用登录后的会话
    if result["success"]:
        # 执行其他操作...
        pass
```

## 8. 帮助

查看详细文档：
- [COURT_ZXFW_SERVICE.md](./COURT_ZXFW_SERVICE.md) - 完整的服务文档
- [STRUCTURE.md](./STRUCTURE.md) - 爬虫架构说明

遇到问题？
- 查看调试截图：`media/automation/screenshots/`
- 查看日志：`logs/api.log`
