# 法院网站验证码自动识别油猴脚本使用指南

## 功能说明

这个油猴脚本可以自动识别法院网站（https://zxfw.court.gov.cn/zxfw）登录页面的验证码，并自动填充到输入框中。

## 安装步骤

### 1. 安装 Tampermonkey 浏览器扩展

- **Chrome/Edge**: 访问 [Chrome Web Store](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo)
- **Firefox**: 访问 [Firefox Add-ons](https://addons.mozilla.org/firefox/addon/tampermonkey/)
- **Safari**: 访问 [App Store](https://apps.apple.com/app/tampermonkey/id1482490089)

### 2. 安装脚本

1. 点击浏览器工具栏中的 Tampermonkey 图标
2. 选择 "创建新脚本"
3. 删除默认内容
4. 复制 `court_captcha_userscript.js` 的全部内容并粘贴
5. 按 `Ctrl+S` (Mac: `Cmd+S`) 保存

### 3. 启动后端 API 服务

脚本需要后端 API 服务来识别验证码。

```bash
cd backend
source venv311/bin/activate
cd apiSystem
python manage.py runserver 8000
```

确保服务运行在 `http://127.0.0.1:8000`

## 使用方法

### 自动模式（推荐）

1. 访问法院网站登录页面：https://zxfw.court.gov.cn/zxfw/#/pagesGrxx/pc/login/index
2. 脚本会自动：
   - 点击切换到"密码登录"标签
   - 等待验证码图片加载
   - 识别验证码并自动填充
3. 你只需要：
   - 输入用户名和密码
   - 点击"登录"按钮
4. 如果验证码错误：
   - 脚本会自动检测错误消息
   - 自动重新识别并填充新的验证码

### 手动触发模式

如果自动模式没有触发，你可以：

1. 手动点击"密码登录"标签
2. 等待几秒，脚本会自动识别验证码
3. 如果验证码输入框为空，脚本会每 5 秒检查一次并重新识别

## 配置选项

在脚本开头的 `CONFIG` 对象中，你可以修改以下配置：

```javascript
const CONFIG = {
    API_URL: 'http://127.0.0.1:8000/api/v1/automation/captcha/recognize',  // API 地址
    CHECK_INTERVAL: 500,      // 检查间隔（毫秒）
    MAX_RETRIES: 3,           // 最大重试次数
    DEBUG: true               // 调试模式（显示详细日志）
};
```

### 修改 API 地址

如果你的后端服务运行在不同的地址或端口，修改 `API_URL`：

```javascript
API_URL: 'http://localhost:8080/api/v1/automation/captcha/recognize'
```

### 关闭调试日志

如果不想看到详细的日志信息，设置 `DEBUG: false`：

```javascript
DEBUG: false
```

## 功能特性

### ✅ 自动化功能

- ✅ 自动切换到密码登录标签
- ✅ 自动等待验证码图片加载
- ✅ 自动识别验证码
- ✅ 自动填充验证码到输入框
- ✅ 自动监听错误消息
- ✅ 验证码错误时自动重新识别

### 🛡️ 智能保护

- 🛡️ 防止重复识别同一张验证码图片
- 🛡️ 最大重试次数限制（默认 3 次）
- 🛡️ API 请求超时保护（10 秒）
- 🛡️ 图片加载超时保护（3 秒）
- 🛡️ 并发处理保护（同时只处理一个请求）

### 📊 监控功能

- 📊 实时日志输出（可在浏览器控制台查看）
- 📊 识别成功/失败状态提示
- 📊 错误消息监听
- 📊 URL 变化自动重新初始化

## 调试方法

### 查看日志

1. 打开浏览器开发者工具（F12）
2. 切换到 "Console" 标签
3. 查看以 `[法院验证码识别]` 开头的日志

### 日志类型

- 🔵 **蓝色 (info)**: 一般信息
- 🟢 **绿色 (success)**: 成功操作
- 🔴 **红色 (error)**: 错误信息
- ⚪ **灰色 (debug)**: 调试信息（仅在 DEBUG 模式下显示）

### 常见问题

#### 1. 脚本没有自动运行

**检查项**:
- Tampermonkey 是否已启用
- 脚本是否已启用
- 是否在正确的页面（登录页面）
- 查看控制台是否有错误信息

**解决方法**:
- 刷新页面
- 检查 Tampermonkey 图标，确保脚本已启用
- 查看控制台日志

#### 2. API 请求失败

**错误信息**: `API 请求失败` 或 `API 请求超时`

**检查项**:
- 后端服务是否正在运行
- API 地址是否正确
- 网络连接是否正常

**解决方法**:
```bash
# 检查后端服务状态
curl http://127.0.0.1:8000/api/v1/health

# 重启后端服务
cd backend/apiSystem
python manage.py runserver 8000
```

#### 3. 验证码识别失败

**错误信息**: `识别失败` 或 `无法识别验证码`

**可能原因**:
- 验证码图片质量差
- 验证码类型不支持
- 后端识别服务异常

**解决方法**:
- 脚本会自动重试（最多 3 次）
- 如果多次失败，可以手动输入验证码
- 检查后端服务日志

#### 4. 验证码输入框未填充

**检查项**:
- XPath 选择器是否正确
- 页面结构是否发生变化
- 输入框是否被禁用

**解决方法**:
- 查看控制台日志
- 检查 XPath 选择器
- 手动测试 XPath 是否能找到元素

#### 5. 跨域问题

**错误信息**: `CORS` 相关错误

**解决方法**:
- 确保脚本头部包含 `@connect` 配置：
  ```javascript
  // @connect      127.0.0.1
  // @connect      localhost
  ```
- 确保后端 CORS 配置正确

## 手动测试 XPath

在浏览器控制台中测试 XPath 是否正确：

```javascript
// 测试密码标签
$x('/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[2]/uni-view[2]')

// 测试验证码图片
$x('/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[2]/uni-image/img')

// 测试验证码输入框
$x('/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[1]/uni-view/uni-input/div/input')

// 测试错误消息
$x('/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[4]')
```

如果返回空数组 `[]`，说明 XPath 不正确，需要更新。

## 更新 XPath 选择器

如果页面结构发生变化，你需要更新脚本中的 XPath 选择器：

1. 在浏览器中右键点击目标元素
2. 选择 "检查" 或 "审查元素"
3. 在开发者工具中右键点击 HTML 元素
4. 选择 "Copy" → "Copy XPath"
5. 在脚本中更新对应的 XPath

## 性能优化

### 减少 API 调用

脚本已实现以下优化：
- 防止重复识别同一张验证码图片
- 并发处理保护
- 智能重试机制

### 调整检查间隔

如果觉得脚本响应太快或太慢，可以调整 `CHECK_INTERVAL`：

```javascript
CHECK_INTERVAL: 1000,  // 增加到 1 秒
```

## 安全说明

### 数据隐私

- 脚本只在本地浏览器运行
- 验证码图片通过本地 API 处理
- 不会上传任何数据到第三方服务器

### API 安全

- 确保后端 API 只在本地运行
- 不要将 API 暴露到公网
- 建议使用防火墙限制访问

## 卸载方法

1. 点击 Tampermonkey 图标
2. 选择 "管理面板"
3. 找到 "法院网站验证码自动识别" 脚本
4. 点击删除图标

## 技术支持

如果遇到问题：

1. 查看浏览器控制台日志
2. 检查后端服务状态
3. 验证 XPath 选择器是否正确
4. 查看本文档的常见问题部分

## 更新日志

### v1.0 (2025-11-30)
- ✨ 初始版本
- ✅ 自动切换到密码登录
- ✅ 自动识别验证码
- ✅ 自动填充验证码
- ✅ 错误监听和自动重试
- ✅ 智能防重复识别
- ✅ 完整的日志系统

## 许可证

MIT License
