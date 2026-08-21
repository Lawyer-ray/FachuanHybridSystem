# 发布公众号

通过微信公众号 API 将文章保存到草稿箱。

## 功能说明

- 支持 HTML / Markdown 两种正文输入格式
- access_token 本地缓存复用（有效期约 2 小时）
- 密钥外置 `.env` 文件，不上传 Git

## 使用方式

```bash
cd skills/自媒体运营/发布公众号

# 1. 安装依赖（使用 uv）
uv pip install -e .

# 2. 复制配置并填写密钥
cp .env.example .env
# 编辑 .env，填入 WECHAT_APPID、WECHAT_APPSECRET、AUTHOR

# 3. 运行（HTML 输入）
python3 cli.py \
    --title "文章标题（≤64 字节）" \
    --digest "文章摘要（≤120 字节）" \
    --html example-article.html

# 4. 或 Markdown 输入
python3 cli.py \
    --title "文章标题" \
    --digest "文章摘要" \
    --markdown article.md
```

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--title` | ✅ | 文章标题，≤64 字节 |
| `--digest` | ✅ | 文章摘要，≤120 字节 |
| `--html` | 二选一 | 正文 HTML 文件路径 |
| `--markdown` | 二选一 | 正文 Markdown 文件路径 |
| `--no-preview` | ❌ | 不在终端打印正文预览 |
| `--force-refresh-token` | ❌ | 强制刷新 access_token |

## 输出说明

成功后在终端输出：
- 文章标题、摘要、草稿 ID
- 提示前往 `mp.weixin.qq.com` 草稿箱发布

**注意**：此工具只保存正文到草稿箱，不处理封面图。
封面图需要在公众号后台手动上传和裁剪（或在另建的 Skill 中处理）。

## 限制说明

- 仅支持已启用「开发→基本配置」的**认证订阅号或服务号**（个人订阅号无法用高级接口）
- Markdown 转换器为极简实现，仅支持标题、段落、加粗、斜体、引用、有序列表和空行
- 网络请求超时：token 15 秒，草稿 30 秒

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
