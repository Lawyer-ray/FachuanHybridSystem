# 案件处理工作流

案件材料的自动化处理工作流,终极目标是 **「案件材料丢进去,产出全套可用的案件材料」**。

通过 skill 的串联调用,将整个案件处理流程自动化:从原始材料(多种格式)的识别与解析,到信息提取、结构化整理、归档分类,最终产出可直接用于案件办理的全套材料。

## 工作流程

1. **Step 0**: 文件识别 - 将各种格式(PDF/DOC/DOCX/图片/OFD 等)统一转为 Markdown,为后续 AI 分析做准备
2. **Step 1**: 按标题拆分 - 将整篇 Markdown 按文书标题拆分为多个独立 .md(每份文书一个,AI 辅助)
3. **Step 2**: 案件信息提取 - 从 Markdown 中提取案件元信息(当事人、案号、法院、案由等,待实现)
4. **Step 3**: 材料分类归档 - 按案件材料类型分类(起诉状、证据清单、判决书等,待实现)
5. **Step 4**: 案件材料整理 - 输出全套可用的案件材料(待实现)

> 后续 skill 将逐步补充,最终形成端到端的案件处理自动化流程。

## 使用方式

### 单独调用

```bash
# 文件识别(将单个文件转为 Markdown)
python -m skills.案件处理.文件识别.scripts /path/to/document.pdf

# 批量识别(扫描整个目录)
python -m skills.案件处理.文件识别.scripts /path/to/case_folder --recursive

# 指定输出目录
python -m skills.案件处理.文件识别.scripts /path/to/document.pdf --output-dir /path/to/md_output

# 按标题拆分(AI 辅助模式)
python -m skills.案件处理.按标题拆分.scripts /path/to/case_material.md --analyze > structure.json
# AI 读取 structure.json 生成 split_map.json
python -m skills.案件处理.按标题拆分.scripts /path/to/case_material.md --apply-map split_map.json output_dir/
```

### 工作流调用

```bash
# 调用整个工作流(待实现)
/案件处理 /path/to/case_folder
```

## Skills 列表

每个 skill 遵循 [Agent Skills Specification](https://agentskills.io/specification),入口为 `SKILL.md`。

| Skill | 说明 | 版本 | 状态 |
|-------|------|------|------|
| [文件识别](./文件识别/) | 接入文档解析服务,将各种格式统一转为 Markdown | 1.1.1 | ✅ 可用 |
| [按标题拆分](./按标题拆分/) | 将整篇 Markdown 按文书标题拆分为多个独立 .md | 1.1.1 | ✅ 可用 |
| 案件信息提取 | 从 Markdown 中提取案件元信息 | - | 🚧 待实现 |
| 材料分类归档 | 按案件材料类型分类 | - | 🚧 待实现 |
| 案件材料整理 | 输出全套可用的案件材料 | - | 🚧 待实现 |

## 目录结构

```
案件处理/
├── README.md                      # 本文件(工作流总览)
├── CHANGELOG.md                   # 工作流变更日志
├── config.example.py              # 配置模板(复制为 config.py 使用,不入库)
├── _shared/                       # 跨 skill 公共模块
│   ├── __init__.py
│   └── http_client.py             # httpx API 客户端(替代 requests)
├── 文件识别/                      # Step 0: 文件格式识别与转换
│   ├── SKILL.md                   # Agent Skills 规范入口
│   ├── CHANGELOG.md
│   ├── scripts/                   # 可执行代码
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py
│   │   ├── converter.py
│   │   ├── detector.py
│   │   ├── formats.py
│   │   └── utils.py
│   ├── references/                # 参考文档
│   │   └── SUPPORTED_FORMATS.md
│   ├── assets/                    # 静态资源
│   │   └── config.example.py
│   └── tests/
│       └── fixtures/
└── 按标题拆分/                    # Step 1: 按文书标题拆分 markdown
    ├── SKILL.md
    ├── CHANGELOG.md
    ├── scripts/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── cli.py
    │   ├── converter.py
    │   ├── detector.py
    │   ├── formats.py
    │   └── utils.py
    ├── references/
    │   └── SPLIT_STRATEGY.md
    └── tests/
        └── fixtures/
```

## 依赖

依赖已在 `backend/pyproject.toml` 中声明,通过 `uv sync` 统一管理:

```bash
cd backend && uv sync
```

| 包 | 用途 |
|---|---|
| httpx | 调用后端 API(与后端 `httpx[http2]==0.28.1` 一致) |

> ⚠️ 不要使用 `pip install` 安装依赖,项目的包管理工具是 `uv`。
> ⚠️ 不要使用 `requests`,项目统一用 `httpx`。

## 认证配置

文件识别 skill 支持三种认证配置方式,按优先级(高 → 低):

1. **CLI 参数**(单次调用):`--token` 或 `--username`/`--password`
2. **环境变量**(会话级):
   - `FACHUAN_API_TOKEN`(JWT Token,优先)
   - `FACHUAN_USERNAME` + `FACHUAN_PASSWORD`(Session 登录)
   - `FACHUAN_BASE_URL`(后端地址,默认 `http://127.0.0.1:8002`)
3. **本地配置文件**(默认值,推荐):复制 `config.example.py` 为 `config.py` 并填入账号

`config.py` 已在 `.gitignore` 中,不会被提交,适合存放团队共享的默认账号:

```bash
cd skills/案件处理
cp config.example.py config.py
# 编辑 config.py 填入账号密码
```

配置完成后,直接调用 skill 即可,无需任何参数:

```bash
python -m skills.案件处理.文件识别.scripts /path/to/file.pdf
```

## 限制

- 文件识别 需要后端服务运行(`http://127.0.0.1:8002`)
- 异步解析后端(mineru/textin)调用需在 SystemConfig 中配置对应 API Key
- 单文件最大等待时间默认 600 秒(可配置)
- 按标题拆分 无依赖,纯本地 Python 标准库即可运行

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
