# 自媒体运营

律所自媒体内容运营工具集合，覆盖微信公众号、视频号等平台。

## 工作流程

1. **发布公众号** — 通过微信公众号 API 保存图文草稿

## 使用方式

### 单独调用

```bash
cd skills/自媒体运营/发布公众号
pip install -r requirements.txt

# 从 HTML 文件发布
python3 cli.py \
    --title "文章标题" \
    --digest "摘要" \
    --html article.html \
    --cover cover.jpg

# 从 Markdown 文件发布
python3 cli.py \
    --title "文章标题" \
    --digest "摘要" \
    --markdown article.md \
    --cover cover.jpg
```

### 命令行快捷调用

```bash
cd skills/自媒体运营/发布公众号
python3 cli.py --help
```

## Skills 列表

| Skill | 说明 | 版本 |
|-------|------|------|
| [发布公众号](./发布公众号/) | 微信公众号图文草稿保存（HTML/Markdown） | 1.0.0 |

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
