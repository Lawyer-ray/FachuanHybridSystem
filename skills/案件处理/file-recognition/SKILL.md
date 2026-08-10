---
name: file-recognition
description: >
  文件格式识别 Skill，接入后端文档解析服务（http://127.0.0.1:8002/api/v1/document-parsing/），
  将 PDF / DOC / DOCX / PPT / XLS / 图片 / OFD / RTF / HTML 等 15+ 种格式统一转为 Markdown，
  为后续 AI 分析和案件处理流程提供标准文本输入。
  当用户上传 PDF/DOC/DOCX/图片/OFD 等文件需要转为 Markdown，或说“文件识别”“转 markdown”
  “解析文档”“识别文件格式”时触发。
compatibility: >
  需要后端服务 http://127.0.0.1:8002 运行；依赖 httpx（已由 _shared/http_client.py 封装）；
  需要 Django Admin 账号或 JWT Token 用于认证。
metadata:
  author: fachuan
  version: "1.1.0"
---

# 文件识别 Skill (V1.1)

接入后端文档解析服务，将各种格式文件统一转为 Markdown，为后续 AI 分析和案件处理流程做准备。

> 本 skill 是“案件处理”工作流的 Step 0，产出 Markdown 供下游 skill（案件信息提取、材料分类等）使用。

## 触发条件

- 用户上传 PDF / DOC / DOCX / 图片 / OFD / RTF 等文件并要求转为 Markdown
- 用户说“文件识别”“转 markdown”“解析文档”“识别文件格式”
- 用户说 `/文件识别`
- 案件处理工作流的 Step 0

## 功能

- 接入 `http://127.0.0.1:8002/api/v1/document-parsing/` 文档解析服务
- 支持 15+ 种文件格式统一转为 Markdown（详见 [references/SUPPORTED_FORMATS.md](./references/SUPPORTED_FORMATS.md)）
- 自动选择合适的解析后端（textin / mineru / local）
- 支持单文件和批量目录扫描（可递归）
- 异步任务自动轮询，同步结果直接返回
- 输出标准 Markdown 文件

## 输入

| 格式 | 处理方式 |
|------|----------|
| 单文件路径 | 直接解析并输出 .md |
| 目录路径 | 扫描目录下所有支持格式（可 `--recursive` 递归） |

## 使用方式

### 单文件识别

```bash
# 基本用法（输出与输入同目录，文件名相同扩展名 .md）
python -m skills.案件处理.file-recognition.scripts /path/to/起诉状.pdf

# 指定输出目录
python -m skills.案件处理.file-recognition.scripts /path/to/起诉状.pdf --output-dir /path/to/md_output

# 指定后端
python -m skills.案件处理.file-recognition.scripts /path/to/起诉状.pdf --backend textin
```

### 批量识别（目录扫描）

```bash
# 扫描目录下所有支持的文件（不递归）
python -m skills.案件处理.file-recognition.scripts /path/to/case_folder

# 递归扫描子目录
python -m skills.案件处理.file-recognition.scripts /path/to/case_folder --recursive
```

### 在 Claude 中调用

```
/文件识别 /path/to/起诉状.pdf
```

## 参数说明

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `input` | - | (必填) | 输入文件或目录路径 |
| `--backend` | `-b` | `auto` | 解析后端：`auto`/`mineru`/`textin`/`local` |
| `--output-dir` | `-o` | 同输入目录 | Markdown 输出目录 |
| `--recursive` | `-r` | `false` | 输入为目录时递归扫描子目录 |
| `--base-url` | - | 环境变量 | 后端服务地址 |
| `--token` | - | 环境变量 | JWT Token |
| `--username` | - | 环境变量 | 登录用户名 |
| `--password` | - | 环境变量 | 登录密码 |
| `--poll-interval` | - | `2.0` | 异步任务轮询间隔（秒） |
| `--poll-timeout` | - | `600` | 异步任务最大等待时间（秒） |
| `--verbose` | `-v` | `false` | 显示详细日志 |

## 认证配置

通过环境变量（推荐）或 CLI 参数提供认证，优先级：CLI 参数 > 环境变量 > 本地 config.py。

```bash
# JWT Token（优先）
export FACHUAN_API_TOKEN='your_jwt_token'

# 或 Session 登录
export FACHUAN_USERNAME='admin'
export FACHUAN_PASSWORD='your_password'  # pragma: allowlist secret

# 可选：自定义后端地址
export FACHUAN_BASE_URL='http://127.0.0.1:8002'
```

也可复制 `assets/config.example.py` 为工作流根目录的 `config.py` 填入账号（config.py 不入库）。

## 输出说明

- **输出文件**：`{原文件名}.md`，默认与输入文件同目录，可通过 `--output-dir` 指定
- **退出码**：`0`=全部成功，`1`=部分失败，`2`=全部失败或参数错误
- **结果汇总**：CLI 末尾打印成功/失败统计

## 后端说明

| 后端 | 名称 | Markdown 输出 | 异步 | 支持格式数 |
|------|------|:---:|:---:|:---:|
| `textin` | TextinParse 云 API | ✅ | ✅ | 15 |
| `mineru` | MinerU 云 API | ✅ | ✅ | 10 |
| `local` | 本地 PyMuPDF + RapidOCR | ❌ | ❌ | 6 |
| `auto` | 自动选择 | - | - | 15 |

`auto` 模式按 `textin > mineru > local` 优先级选择支持当前格式的后端。

> 注：`local` 后端只支持纯文本输出；若选 `auto` 且格式仅 `local` 支持（如 BMP/TIFF），会输出纯文本到 .md 文件。

各后端详细支持格式见 [references/SUPPORTED_FORMATS.md](./references/SUPPORTED_FORMATS.md)。

## 工作流集成

本 skill 是“案件处理”工作流的 Step 0：

```
案件材料（PDF/DOC/图片等）
        ↓
   [文件识别]  ← 本 skill，产出 Markdown
        ↓
   [案件信息提取]（待实现）
        ↓
   [材料分类归档]（待实现）
        ↓
   全套可用案件材料
```

## 模块结构

```
file-recognition/
├── SKILL.md                     # Skill 说明（本文件）
├── CHANGELOG.md                 # 变更日志
├── scripts/                     # 可执行脚本
│   ├── __init__.py              # 入口（导出 recognize_file / recognize_files）
│   ├── __main__.py              # 模块执行入口
│   ├── cli.py                   # 命令行入口
│   ├── converter.py             # 调用 API 解析并保存 Markdown
│   ├── detector.py              # 文件格式检测、后端选择、目录扫描
│   ├── formats.py               # 支持格式定义、后端配置
│   └── utils.py                 # 工具函数（输出路径生成、结果汇总）
├── references/                  # 参考资料
│   └── SUPPORTED_FORMATS.md     # 各后端支持的格式详细列表
├── assets/                      # 资源文件
│   └── config.example.py        # 配置模板
└── tests/                       # 测试
    └── fixtures/
        └── sample.txt
```

## 限制

- 需要后端服务运行（`http://127.0.0.1:8002`）
- 异步解析后端（mineru/textin）需在 SystemConfig 中配置对应 API Key：`MINERU_API_KEY`、`TEXTIN_APP_ID` + `TEXTIN_SECRET_CODE`
- 单文件最大等待时间默认 600 秒（可通过 `--poll-timeout` 调整）
- `local` 后端不支持 Markdown 输出，会降级为纯文本

## 依赖

HTTP 客户端由 `skills/案件处理/_shared/http_client.py` 统一封装（httpx），不使用 requests。

> ⚠️ 不要使用 `pip install`，项目包管理工具是 `uv`。

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
