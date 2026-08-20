# 自媒体运营 Skill

微信公众号草稿箱发布工具，支持通过 API 将文章保存为草稿。

## 前置条件

```bash
# 1. 安装依赖
pip install httpx python-dotenv

# 2. 复制配置模板并填写

cp skills/自媒体运营/.env.example skills/自媒体运营/.env
# 编辑 skills/自媒体运营/.env，填写你的 AppID、AppSecret、作者名称
```

## 快速使用

```bash
cd skills/自媒体运营
python3 wechat_draft.py \
    --title "文章标题" \
    --digest "文章摘要" \
    --html ./article.html \
    --cover ./cover.jpg
```

## 功能

- ✅ 自动获取 access_token（本地缓存，避免重复请求）
- ✅ 上传封面图到微信服务器
- ✅ 创建图文草稿
- ✅ 纯 httpx 实现，异步高效
- ✅ 密钥外置 .env，不上传 Git
