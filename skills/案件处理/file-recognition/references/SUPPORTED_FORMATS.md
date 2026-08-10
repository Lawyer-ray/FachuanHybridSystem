# 支持的文件格式

文件识别 Skill 支持的文件格式由各解析后端的能力矩阵决定。任一后端支持的格式即视为支持。

## 格式总览

| 类别 | 格式 |
|------|------|
| 文档 | PDF / DOC / DOCX / PPT / PPTX / XLS / XLSX / OFD / RTF |
| 图片 | JPG / JPEG / PNG / BMP / TIFF |
| 其他 | HTML / CSV / TXT |

去重后共 15 种格式。

## 各后端支持矩阵

### textin（TextinParse 云 API）

Markdown 输出：✅ | 异步：✅ | 支持格式数：15

| # | 格式 | 类别 |
|---|------|------|
| 1 | pdf | 文档 |
| 2 | doc | 文档 |
| 3 | docx | 文档 |
| 4 | ppt | 文档 |
| 5 | pptx | 文档 |
| 6 | xls | 文档 |
| 7 | xlsx | 文档 |
| 8 | jpg | 图片 |
| 9 | jpeg | 图片 |
| 10 | png | 图片 |
| 11 | ofd | 文档 |
| 12 | rtf | 文档 |
| 13 | html | 其他 |
| 14 | csv | 其他 |
| 15 | txt | 其他 |

### mineru（MinerU 云 API）

Markdown 输出：✅ | 异步：✅ | 支持格式数：10

| # | 格式 | 类别 |
|---|------|------|
| 1 | pdf | 文档 |
| 2 | doc | 文档 |
| 3 | docx | 文档 |
| 4 | ppt | 文档 |
| 5 | pptx | 文档 |
| 6 | xls | 文档 |
| 7 | xlsx | 文档 |
| 8 | jpg | 图片 |
| 9 | jpeg | 图片 |
| 10 | png | 图片 |

### local（本地 PyMuPDF + RapidOCR）

Markdown 输出：❌（仅纯文本） | 异步：❌（同步） | 支持格式数：6

| # | 格式 | 类别 |
|---|------|------|
| 1 | pdf | 文档 |
| 2 | jpg | 图片 |
| 3 | jpeg | 图片 |
| 4 | png | 图片 |
| 5 | bmp | 图片 |
| 6 | tiff | 图片 |

## auto 模式选择逻辑

`auto` 模式按 `textin > mineru > local` 优先级选择支持当前格式的后端：

1. 优先 `textin`（格式覆盖最广，15 种）
2. `textin` 不支持则 `mineru`（10 种）
3. 都不支持则 `local`（6 种）

### 仅 local 支持的格式

以下格式只有 `local` 后端支持，`auto` 模式会选择 `local`（输出纯文本到 .md）：

- **BMP**
- **TIFF**

### 仅 textin 支持的格式

以下格式只有 `textin` 后端支持：

- **OFD**
- **RTF**
- **HTML**
- **CSV**
- **TXT**

## 后端特性对比

| 后端 | Markdown | 异步 | 云 API | 需 API Key | 格式数 |
|------|:---:|:---:|:---:|:---:|:---:|
| textin | ✅ | ✅ | ✅ | TEXTIN_APP_ID + TEXTIN_SECRET_CODE | 15 |
| mineru | ✅ | ✅ | ✅ | MINERU_API_KEY | 10 |
| local | ❌ | ❌ | ❌ | 无 | 6 |
| auto | - | - | - | 视实际后端 | 15 |

## 格式检测说明

- 格式检测基于文件扩展名（小写、去点），不读取文件头魔数
- 无扩展名的文件视为不支持
- 大小写不敏感：`.PDF` 与 `.pdf` 等价

| 输入 | 标准化后 |
|------|----------|
| .JPG | jpg |
| .JPEG | jpeg |
| .PDF | pdf |
| .Xlsx | xlsx |

## 数据来源

本文件由 `scripts/formats.py` 中的 `BACKEND_FORMATS` 常量定义。如需新增格式支持，修改该常量后同步更新本文件。
