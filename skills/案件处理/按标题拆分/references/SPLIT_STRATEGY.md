# 拆分策略详解

本文件详细说明按标题拆分 skill 三种工作模式的工作原理、适用场景，以及 `split_map.json` 的 schema。

## 概览

| 模式 | 触发参数 | 谁决定拆分点 | 适用场景 | 准确度 |
|------|----------|--------------|----------|--------|
| 规则模式 | 默认 / `--level N` | 规则（按标题层级） | 标题规范的文档 | 低（对真实材料） |
| AI 分析模式 | `--analyze` | 输出候选供 AI 判断 | 真实案件材料 | - |
| AI 映射模式 | `--apply-map MAP_FILE` | AI（基于分析结果） | 配合分析模式 | 高 |

真实案件材料的 markdown 标题层级通常混乱（法院名被标成标题、正文被误识别为标题、EMS 封套混入等），规则模式无法准确切分，因此推荐 **AI 辅助三步法**（分析模式 + 映射模式）。

---

## 模式一：规则模式（兜底）

### 工作原理

1. 扫描 markdown 全文，识别所有候选标题行（`#`~`######`）。
2. 筛选出指定层级（`--level N`，默认 `2` 即 `##`）的标题。
3. 每个目标标题作为一个片段的起点，到下一个目标标题前结束。
4. 第一个目标标题之前的内容（文件开头）单独作为一个"前言"片段。
5. 噪音片段（基于关键词匹配）文件名加 `00_noise_` 前缀。

### 适用场景

- 文档标题层级规范、统一（如手工编写的文档）
- 快速验证 / 临时切分
- 不要求高准确度的场景

### 局限

- 真实案件材料标题层级混乱：法院名、落款、正文片段常被误识别为标题
- 无法区分"文书标题"和"正文中的小标题"
- 无法识别文书类型

### 调用

```bash
python -m skills.案件处理.按标题拆分.scripts input.md [--level N] [output_dir]
```

---

## 模式二：AI 分析模式（`--analyze`）

### 工作原理

本模块只做"检测"，不做"判断"。哪些候选标题是真正的拆分点，由 AI 决定。

1. 扫描 markdown 全文，识别所有候选标题行：
   - markdown 标题行（`#`~`######`），记录层级 `level`（1-6）
   - 全行加粗的短行（`**xxx**` 或 `__xxx__`，行长度 < 80 字符），记 `level=0`
2. 为每个候选标题提取上下文：前 200 字符（`context_before`）+ 后 200 字符（`context_after`）。
3. 用 `NOISE_KEYWORDS` 初步标记疑似噪音（EMS 封套、填写说明等）。
4. 输出结构化 JSON 到 stdout，含候选标题的 `text`、`level`、`context_before`、`context_after`、`is_noise`。

### 输出 JSON 结构

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

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_file` | string | 源文件绝对路径 |
| `total_lines` | int | 文件总行数 |
| `total_chars` | int | 文件总字符数 |
| `candidate_count` | int | 候选标题数量 |
| `candidates[].index` | int | 候选序号（0-based） |
| `candidates[].line_no` | int | 行号（0-based） |
| `candidates[].text` | string | 标题文本（已去除 `#` 和 `**` 标记） |
| `candidates[].raw` | string | 原始行内容 |
| `candidates[].level` | int | 标题层级（1-6 对应 `#`~`######`，0 表示加粗行） |
| `candidates[].is_noise` | bool | 是否疑似噪音（基于关键词匹配，仅供参考） |
| `candidates[].context_before` | string | 前 200 字符 |
| `candidates[].context_after` | string | 后 200 字符 |

### 适用场景

- 真实案件材料（标题层级混乱）
- 需要 AI 语义理解来判断拆分点的场景
- 作为 AI 映射模式的前置步骤

### 调用

```bash
python -m skills.案件处理.按标题拆分.scripts input.md --analyze > structure.json
```

---

## 模式三：AI 映射模式（`--apply-map`）

### 工作原理

接收 AI 生成的拆分方案 JSON（`split_map.json`），执行实际切分：

1. 读取 `split_map.json`（AI 生成的拆分方案列表）。
2. 按 `start_line` 排序。
3. 对每个片段：按 `start_line` / `end_line` 从原文提取行，写入以 `{序号}_{name}` 命名的 .md 文件。
4. 噪音片段（`is_noise: true`）文件名加 `00_noise_` 前缀。
5. 过短的噪音片段（< `MIN_CHUNK_CHARS`，默认 50 字符）跳过。
6. 行号做边界保护：`start`/`end` 被 clamp 到 `[0, total_lines-1]`，且 `end >= start`。

### 适用场景

- 配合分析模式使用：分析模式输出候选 → AI 判断 → 映射模式执行
- 需要 AI 语义理解保证准确度的场景

### 调用

```bash
python -m skills.案件处理.按标题拆分.scripts input.md --apply-map split_map.json [output_dir]
```

---

## AI 辅助三步法流程

```
input.md
   │
   ▼  --analyze
structure.json（候选标题 + 上下文）
   │
   ▼  AI（trae/claude code）读取并判断
split_map.json（拆分方案：每个片段的 name / start_line / end_line / type / is_noise）
   │
   ▼  --apply-map
output_dir/（多个独立 .md）
```

### AI 判断要点（hint）

AI 拿到 `structure.json` 后，根据候选标题的 `text`、`level`、`context_before`、`context_after` 判断：

1. 哪些候选标题是"一份独立法律文书的开始"（拆分点）
2. 哪些是噪音（EMS 封套 / 填写说明 / 正文片段，标记 `is_noise: true`）
3. 为每个拆分片段起一个简洁的文件名（`name`）和文书类型（`type`）
4. `start_line` 和 `end_line` 是行号（0-based），`end_line` 是该片段最后一行
5. 第一个片段的 `start_line` 通常为 0（包含文件开头的非标题内容）
6. 相邻片段的 `end_line + 1 = 下一个片段的 start_line`

---

## `split_map.json` Schema

AI 生成的拆分方案，是一个 JSON 数组，每项描述一个拆分片段：

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

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 否 | 文件名（会清洗非法字符，缺失时用 `片段{序号}`）。最大 50 字符，超长截断 |
| `start_line` | int | 是 | 起始行号（0-based） |
| `end_line` | int | 否 | 结束行号（0-based，含该行）。缺失时取文件最后一行 |
| `type` | string | 否 | 文书类型（起诉状 / 传票 / 通知书等）。供后续处理参考，不影响拆分 |
| `is_noise` | bool | 否 | 是否噪音片段。默认 `false`。为 `true` 时文件名加 `00_noise_` 前缀 |

### 行号约定

- 行号是 **0-based**（第一行为 0）。
- `end_line` **包含该行**（闭区间 `[start_line, end_line]`）。
- 行号会被 clamp 到文件实际行数范围内，`end_line < start_line` 时取 `end_line = start_line`。

### 文件名清洗规则

- 非法字符 `\ / : * ? " < > |` 及控制字符（`\n \r \t`）替换为下划线 `_`
- 压缩连续下划线
- 去除首尾空白和下划线
- 限制长度 50 字符（超长截断）
- 空名时回退为 `未命名`

### 输出文件命名

```
{序号}_{清洗后name}.md        # 普通片段
00_noise_{清洗后name}.md      # 噪音片段
```

序号补零到与总数等宽（至少 2 位），便于文件管理器排序。

---

## 已知文书类型关键词

供 AI 判断文书类型时参考（非硬编码规则，定义在 `scripts/formats.py` 的 `DOCUMENT_TYPE_KEYWORDS`）：

起诉状、答辩状、反诉状、上诉状、再审申请、传票、应诉通知书、举证通知书、告知书、送达回证、授权委托书、法定代表人证明、诉讼须知、不予受理通知书、仲裁裁决书、判决书、裁定书、调解书、证据清单、代理词、辩护词、申请书、EMS封套。

### 噪音关键词

`NOISE_KEYWORDS`（用于初步标记候选标题，非硬过滤）：邮政特快专递封套、EMS业务使用说明、收件人、寄件人、业务使用说明、填写说明。

---

## 设计决策

- **不内置 LLM 调用**：遵循项目约定（用 trae/claude code 的 token，不用后端 LLM）
- **AI 辅助模式与合同编号 skill 一致**：输出 JSON → AI 判断 → 应用映射
- **规则模式仅作兜底**：实测真实案件材料标题层级混乱，规则无法准确切分
- **检测与判断分离**：`detector.py` 只做检测，不做判断；判断由 AI 或规则完成
