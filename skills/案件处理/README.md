# 案件处理工作流

案件材料的自动化处理工作流,终极目标是 **「案件材料丢进去,产出全套可用的案件材料」**。

通过 skill 的串联调用,将整个案件处理流程自动化:从原始材料(多种格式)的识别与解析,到信息提取、结构化整理、归档分类,最终产出可直接用于案件办理的全套材料。

## 工作流程

1. **Step 0**: 文件识别 - 将各种格式(PDF/DOC/DOCX/图片/OFD 等)统一转为 Markdown,为后续 AI 分析做准备
2. **Step 1**: 案件信息提取 - 从 Markdown 中提取案件元信息(当事人、案号、法院、案由等,待实现)
3. **Step 2**: 材料分类归档 - 按案件材料类型分类(起诉状、证据清单、判决书等,待实现)
4. **Step 3**: 案件材料整理 - 输出全套可用的案件材料(待实现)

> 后续 skill 将逐步补充,最终形成端到端的案件处理自动化流程。

## 使用方式

### 单独调用

```bash
# 文件识别(将单个文件转为 Markdown)
python -m skills.案件处理.文件识别 /path/to/document.pdf

# 批量识别(扫描整个目录)
python -m skills.案件处理.文件识别 /path/to/case_folder --recursive

# 指定输出目录
python -m skills.案件处理.文件识别 /path/to/document.pdf --output-dir /path/to/md_output

# 在 Claude 中调用
/文件识别 /path/to/document.pdf
```

### 工作流调用

```bash
# 调用整个工作流(待实现)
/案件处理 /path/to/case_folder
```

## Skills 列表

| Skill | 说明 | 版本 | 状态 |
|-------|------|------|------|
| [文件识别](./文件识别/) | 接入文档解析服务,将各种格式统一转为 Markdown | 1.0.0 | ✅ 可用 |
| 案件信息提取 | 从 Markdown 中提取案件元信息 | - | 🚧 待实现 |
| 材料分类归档 | 按案件材料类型分类 | - | 🚧 待实现 |
| 案件材料整理 | 输出全套可用的案件材料 | - | 🚧 待实现 |

## 目录结构

```
案件处理/
├── README.md              # 本文件
├── CHANGELOG.md           # 工作流变更日志
├── utils.py               # 公共工具(API 客户端,跨 skill 共享)
└── 文件识别/              # Step 0: 文件格式识别与转换
    ├── README.md          # Skill 说明
    ├── CHANGELOG.md       # Skill 变更日志
    ├── __init__.py        # 入口(导出 recognize_file / recognize_files)
    ├── __main__.py        # 模块执行入口
    ├── formats.py         # 支持格式定义、后端配置
    ├── detector.py        # 文件格式检测、后端选择
    ├── converter.py       # 调用 API 解析并保存 Markdown
    ├── utils.py           # 工具函数
    └── cli.py             # 命令行入口
```

## 依赖

依赖已在 `backend/pyproject.toml` 中声明,通过 `uv sync` 统一管理:

```bash
cd backend && uv sync
```

| 包 | 用途 |
|---|---|
| requests | 调用后端 API |

> ⚠️ 不要使用 `pip install` 安装依赖,项目的包管理工具是 `uv`。

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
python -m skills.案件处理.文件识别 /path/to/file.pdf
```

## 限制

- 需要后端服务运行(`http://127.0.0.1:8002`)
- 异步解析后端(mineru/textin)调用需在 SystemConfig 中配置对应 API Key
- 单文件最大等待时间默认 600 秒(可配置)

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
