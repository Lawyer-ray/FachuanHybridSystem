# 文件识别 Skill

接入后端文档解析服务,将各种格式文件统一转为 Markdown,为后续 AI 分析做准备。

## 功能

- 接入 `http://127.0.0.1:8002/api/v1/document-parsing/` 文档解析服务
- 支持 15+ 种文件格式统一转为 Markdown:
  - **文档**: PDF / DOC / DOCX / PPT / PPTX / XLS / XLSX / OFD / RTF
  - **图片**: JPG / JPEG / PNG / BMP / TIFF
  - **其他**: HTML / CSV / TXT
- 自动选择合适的解析后端(textin / mineru / local)
- 支持单文件和批量目录扫描(可递归)
- 异步任务自动轮询,同步结果直接返回
- 输出标准 Markdown 文件,供下游 skill(案件信息提取、材料分类等)使用

## 使用方式

### 单文件识别

```bash
# 基本用法(输出与输入同目录,文件名相同扩展名 .md)
python -m skills.案件处理.文件识别 /path/to/起诉状.pdf

# 指定输出目录
python -m skills.案件处理.文件识别 /path/to/起诉状.pdf --output-dir /path/to/md_output

# 指定后端
python -m skills.案件处理.文件识别 /path/to/起诉状.pdf --backend textin

# 在 Claude 中调用
/文件识别 /path/to/起诉状.pdf
```

### 批量识别(目录扫描)

```bash
# 扫描目录下所有支持的文件(不递归)
python -m skills.案件处理.文件识别 /path/to/case_folder

# 递归扫描子目录
python -m skills.案件处理.文件识别 /path/to/case_folder --recursive
```

### 认证配置

通过环境变量(推荐)或 CLI 参数提供认证:

```bash
# 方式 1:JWT Token(优先)
export FACHUAN_API_TOKEN='your_jwt_token'

# 方式 2:用户名密码(Session 登录)
export FACHUAN_USERNAME='admin'
export FACHUAN_PASSWORD='your_password'  # pragma: allowlist secret

# 可选:自定义后端地址
export FACHUAN_BASE_URL='http://127.0.0.1:8002'

# 也可以通过 CLI 参数覆盖
python -m skills.案件处理.文件识别 /path/to/file.pdf --token 'xxx'
python -m skills.案件处理.文件识别 /path/to/file.pdf --username admin --password 'xxx'
```

## 参数说明

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `input` | - | (必填) | 输入文件或目录路径 |
| `--backend` | `-b` | `auto` | 解析后端:`auto`/`mineru`/`textin`/`local` |
| `--output-dir` | `-o` | 同输入目录 | Markdown 输出目录 |
| `--recursive` | `-r` | `false` | 输入为目录时递归扫描子目录 |
| `--base-url` | - | 环境变量 | 后端服务地址 |
| `--token` | - | 环境变量 | JWT Token |
| `--username` | - | 环境变量 | 登录用户名 |
| `--password` | - | 环境变量 | 登录密码 |
| `--poll-interval` | - | `2.0` | 异步任务轮询间隔(秒) |
| `--poll-timeout` | - | `600` | 异步任务最大等待时间(秒) |
| `--verbose` | `-v` | `false` | 显示详细日志 |

## 输出说明

- **输出文件**:`{原文件名}.md`,默认与输入文件同目录,可通过 `--output-dir` 指定
- **退出码**:
  - `0`:全部成功
  - `1`:部分失败
  - `2`:全部失败或参数错误
- **结果汇总**:CLI 末尾打印成功/失败统计

## 后端说明

| 后端 | 名称 | Markdown 输出 | 异步 | 支持格式数 |
|------|------|:---:|:---:|:---:|
| `textin` | TextinParse 云 API | ✅ | ✅ | 15 |
| `mineru` | MinerU 云 API | ✅ | ✅ | 10 |
| `local` | 本地 PyMuPDF + RapidOCR | ❌ | ❌ | 6 |
| `auto` | 自动选择 | - | - | 15 |

`auto` 模式会按 `textin > mineru > local` 的优先级选择支持当前格式的后端。

> 注:`local` 后端只支持纯文本输出,不支持 Markdown;若选 `auto` 且格式仅 `local` 支持(如 BMP/TIFF),会输出纯文本内容到 .md 文件。

## 模块结构

```
文件识别/
├── __init__.py    # 入口(导出 recognize_file / recognize_files)
├── __main__.py    # 模块执行入口
├── formats.py     # 支持格式定义、后端配置
├── detector.py    # 文件格式检测、后端选择、目录扫描
├── converter.py   # 调用 API 解析并保存 Markdown
├── utils.py       # 工具函数(输出路径生成、结果汇总)
└── cli.py         # 命令行入口
```

## 工作流集成

本 skill 是"案件处理"工作流的 Step 0,产出 Markdown 后供下游 skill 使用:

```
案件材料(PDF/DOC/图片等)
        ↓
   [文件识别]  ← 本 skill
        ↓
   Markdown
        ↓
   [案件信息提取](待实现)
        ↓
   [材料分类归档](待实现)
        ↓
   [案件材料整理](待实现)
        ↓
   全套可用案件材料
```

## 依赖

依赖已在 `backend/pyproject.toml` 中声明,通过 `uv sync` 统一管理:

| 包 | 用途 |
|---|---|
| requests | 调用后端 API |

> ⚠️ 不要使用 `pip install`,项目的包管理工具是 `uv`。

## 限制

- 需要后端服务运行(`http://127.0.0.1:8002`)
- 异步解析后端(mineru/textin)调用需在 SystemConfig 中配置对应 API Key:
  - `MINERU_API_KEY`
  - `TEXTIN_APP_ID` + `TEXTIN_SECRET_CODE`
- 单文件最大等待时间默认 600 秒(可通过 `--poll-timeout` 调整)
- `local` 后端不支持 Markdown 输出,会降级为纯文本

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
