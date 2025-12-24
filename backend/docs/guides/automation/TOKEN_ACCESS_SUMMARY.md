# Token 查看和管理 - 快速指南

## 🎯 在 Admin 后台查看 Token

### 方式 1: 直接访问（推荐）

```
http://localhost:8000/admin/automation/courttoken/
```

### 方式 2: 通过导航

1. 访问 Django Admin: `http://localhost:8000/admin/`
2. 找到 **Automation** 应用分组
3. 点击 **Token管理** 链接

## 📋 可以看到什么

在 Token 管理页面，你可以看到：

- ✅ 所有保存的 Token 列表
- ✅ Token 的状态（有效/过期）
- ✅ Token 的剩余有效时间
- ✅ 完整的 Token 字符串（可复制）
- ✅ Token 的创建和过期时间

## 🔍 主要功能

### 1. 查看 Token 列表

列表显示所有 Token，包括：
- 网站名称（如 court_zxfw）
- 账号
- Token 预览（前 20 个字符）
- 状态（✅ 有效 / ❌ 已过期）
- 过期时间

### 2. 搜索 Token

可以按以下条件搜索：
- 网站名称
- 账号
- Token 内容

### 3. 过滤 Token

可以按以下条件过滤：
- 网站名称
- Token 类型
- 创建时间
- 过期时间

### 4. 查看完整 Token

点击某个 Token 记录，可以：
- 查看完整的 Token 字符串
- 复制 Token 用于脚本或 API 调用
- 查看剩余有效时间

### 5. 删除 Token

可以删除不需要的或已过期的 Token：
- 单个删除：点击记录 → 删除按钮
- 批量删除：勾选多个 → 选择"删除已过期的 Token"

## 🚀 快速操作

### 查看某个账号的 Token

1. 访问 Token 管理页面
2. 在搜索框输入账号
3. 点击搜索

### 复制 Token 使用

1. 点击某个 Token 记录
2. 在"完整 Token"文本框中全选（Ctrl+A / Cmd+A）
3. 复制（Ctrl+C / Cmd+C）
4. 在脚本中使用

### 清理过期 Token

1. 访问 Token 管理页面
2. 勾选要删除的 Token（或全选）
3. 选择"删除已过期的 Token"操作
4. 点击"执行"

## 📊 Token 状态说明

| 状态 | 显示 | 说明 |
|------|------|------|
| 有效 | ✅ 绿色 | Token 仍在有效期内 |
| 即将过期 | 🟠 橙色 | 剩余时间 < 30 分钟 |
| 即将过期 | 🔴 红色 | 剩余时间 < 5 分钟 |
| 已过期 | ❌ 红色 | Token 已过期，需要重新登录 |

## 💡 注意事项

1. **只读模式**: Token 管理页面是只读的，不能手动添加或修改 Token
2. **自动创建**: Token 只能通过测试登录自动创建
3. **安全性**: 不要将 Token 分享给他人
4. **及时刷新**: 关注即将过期的 Token，及时重新登录

## 🔗 相关链接

| 功能 | URL |
|------|-----|
| **Token 管理** | http://localhost:8000/admin/automation/courttoken/ |
| 测试登录（创建 Token） | http://localhost:8000/admin/automation/testcourt/ |
| Cookie 管理 | http://localhost:8000/admin/automation/scrapercookie/ |
| 任务管理 | http://localhost:8000/admin/automation/scrapertask/ |

## 📚 详细文档

- [Token Admin 管理指南](./TOKEN_ADMIN_GUIDE.md) - 完整的 Admin 使用文档
- [Token 服务使用指南](./TOKEN_SERVICE_GUIDE.md) - API 使用文档
- [快速开始指南](./QUICK_START_TOKEN.md) - 5 分钟快速上手

---

**提示**: 如果看不到 Token 管理菜单，请确保已执行数据库迁移：`make migrate-token`
