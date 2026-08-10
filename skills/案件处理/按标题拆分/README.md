# 按标题拆分 Skill

将一个包含多份法律文书的 markdown 文件,按标题拆分为多个独立的 .md 文件。

## 功能

- 将"文件识别"skill 产出的整篇 md,拆分为每份文书一个 md
- **AI 辅助模式**:输出候选标题结构 JSON,由 AI(trade/claude code)判断拆分点,准确识别文书边界
- **规则模式**(兜底):按 markdown 指定层级标题切分
- 自动识别噪音片段(EMS 封套、填写说明等),单独标记
- 拆分后的文件按序号命名,便于排序和后续处理

## 适用场景

案件材料 PDF 经"文件识别"skill 转为单个 md 后,通常包含多份文书:
- EMS 封套 / 送达回证 / 传票
- 应诉通知书 / 举证通知书 / 告知书
- 授权委托书 / 法定代表人证明
- 诉讼须知 / 民事起诉状
- 仲裁裁决书 / 证据清单 / 银行流水 ...

本 skill 将其拆分为每份文书一个 md,便于后续单独处理(信息提取、分类归档等)。

## 使用方式

### AI 辅助模式(推荐,适合真实案件材料)

真实案件材料的 markdown 标题层级混乱(法院名被标成标题、正文被误识别为标题等),
规则模式无法准确切分,需用 AI 辅助模式:

```bash
# 第一步:分析文档结构,输出候选标题 JSON
python -m skills.案件处理.按标题拆分 input.md --analyze > structure.json

# 第二步:AI(trade/claude code)读取 structure.json
# AI 根据候选标题的 text、level、context_before、context_after 理解文档结构
# AI 生成 split_map.json:
#   [
#     {"name": "EMS封套", "start_line": 8, "end_line": 63, "type": "EMS封套", "is_noise": true},
#     {"name": "送达回证", "start_line": 64, "end_line": 140, "type": "送达回证"},
#     {"name": "传票", "start_line": 141, "end_line": 168, "type": "传票"},
#     ...
#   ]

# 第三步:按 AI 生成的拆分方案执行切分
python -m skills.案件处理.按标题拆分 input.md --apply-map split_map.json output_dir/

# 在 Claude 中调用
/按标题拆分 input.md --analyze
/按标题拆分 input.md --apply-map split_map.json
```

### 规则模式(兜底,适合标题规范的文档)

```bash
# 按 ## 标题切分(默认)
python -m skills.案件处理.按标题拆分 input.md

# 按 ### 标题切分
python -m skills.案件处理.按标题拆分 input.md --level 3

# 指定输出目录
python -m skills.案件处理.按标题拆分 input.md output_dir/
```

> ⚠️ 规则模式对真实案件材料效果不好(标题层级混乱),建议优先使用 AI 辅助模式。

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `input` | 输入 markdown 文件路径 | (必填) |
| `output_dir` | 输出目录 | `{stem}_split/` |
| `--analyze` | 分析模式:输出候选标题 JSON 到 stdout | - |
| `--apply-map MAP_FILE` | AI 映射模式:读取拆分方案 JSON 并执行 | - |
| `--level N` | 规则模式:按第 N 级标题切分 | `2` |
| `--verbose` | 显示详细日志 | `false` |

## 输出说明

- **输出目录**:`{原文件名}_split/`(可自定义)
- **文件命名**:`{序号}_{文书名}.md`,如 `01_民事起诉状.md`、`02_传票.md`
- **噪音片段**:文件名前缀 `00_noise_`,如 `00_noise_EMS封套.md`
- **序号补零**:便于文件管理器中按顺序排序

### analyze 模式输出 JSON 结构

```json
{
  "source_file": "/path/to/input.md",
  "total_lines": 6500,
  "total_chars": 148712,
  "candidate_count": 30,
  "candidates": [
    {
      "index": 0,
      "line_no": 8,
      "text": "邮政特快专递封套EMS业务使用说明",
      "raw": "# 邮政特快专递封套EMS业务使用说明",
      "level": 1,
      "is_noise": true,
      "context_before": "...前 200 字符...",
      "context_after": "...后 200 字符..."
    }
  ],
  "hint": "请根据候选标题的 text、level、context_before、context_after 判断..."
}
```

### split_map.json 格式(AI 生成)

```json
[
  {
    "name": "EMS封套",
    "start_line": 8,
    "end_line": 63,
    "type": "EMS封套",
    "is_noise": true
  },
  {
    "name": "送达回证",
    "start_line": 64,
    "end_line": 140,
    "type": "送达回证"
  }
]
```

字段说明:
- `name`: 文件名(会清洗非法字符)
- `start_line` / `end_line`: 行号(0-based,end_line 含该行)
- `type`: 文书类型(起诉状/传票/通知书等,可选)
- `is_noise`: 是否噪音片段(EMS 封套/填写说明等,可选,默认 false)

## 已知文书类型

供 AI 判断时参考(非硬编码规则):

起诉状、答辩状、反诉状、上诉状、再审申请、传票、应诉通知书、举证通知书、
告知书、送达回证、授权委托书、法定代表人证明、诉讼须知、不予受理通知书、
仲裁裁决书、判决书、裁定书、调解书、证据清单、代理词、辩护词、申请书、EMS封套

## 模块结构

```
按标题拆分/
├── __init__.py    # 入口(导出 analyze_structure / apply_split_map / split_document)
├── __main__.py    # 模块执行入口
├── formats.py     # 候选标题规则、文书类型关键词、拆分配置
├── detector.py    # 候选标题检测、结构分析(JSON 输出)
├── converter.py   # 拆分执行(apply_split_map / split_document)
├── utils.py       # 工具函数(文件名清洗、结果汇总)
└── cli.py         # 命令行入口
```

## 工作流集成

本 skill 是"案件处理"工作流的 Step 1,接收"文件识别"的输出:

```
案件材料(PDF/DOC/图片等)
        ↓
   [文件识别]        ← Step 0:格式转换
        ↓
   整篇 Markdown
        ↓
   [按标题拆分]      ← Step 1:本 skill
        ↓
   多个独立 .md(每份文书一个)
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

无额外依赖,仅使用 Python 标准库。

## 限制

- 规则模式对真实案件材料效果有限(标题层级混乱),需用 AI 辅助模式
- AI 辅助模式需要 trade/claude code 等 AI agent 配合(读取 JSON、生成拆分方案)
- 输入必须是 .md 文件(先用"文件识别"skill 转换)

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
