---
name: materials-parsing
description: 读取归档材料正文、解析文档、提取表格内容的指引。当用户要「看看这份材料写了什么」「提取合同正文」「解析 PDF/表格」时使用。
---

# 材料与正文

## 已预处理的材料包：优先读 draft segments，不要重新解析

材料预处理（material-prep）里做过「自动识别」的材料包，分段正文（Markdown）
已存在收件箱消息的 draft_state 里，且可能经过律师逐字核对——**这是质量最高
的正文来源，优先于任何重新解析**。

用 `get_material_draft_segments(message_id)` 读（message_id 即材料包 ID，
材料预处理页 URL `/material-prep/<id>` 里的数字）：

1. 先不传 `segment_index` 调一次，拿段目录（段名/类型/页区间/quality_flags/
   md_chars）；`truncated=true` 时用 `offset` 翻页看全目录。
2. 对需要的段传 `segment_index=<下标>` 取 md 全文；`md_truncated=true` 时
   以 `md_offset=next_md_offset` 续读同一段，直到读全。
3. `quality_flags` 非空或 `review_flag` 提示复核的段，引用其内容前提醒律师
   该段识别质量存疑；`md_chars=0` 的段没有正文（多为照片/手写页），不要
   当作「该材料无内容」下结论。

**不要**对这类材料包再调 `extract_document_text` / `parse_document` 做 base64
上传重解析：重解析拿不到律师的人工校对成果，质量更差且重复计费。
`total_segs=0`（从未识别）时才回落到下面的解析路径。

## 归档材料的正文不在数据库里

要读某份材料的实际内容，用 `extract_document_text`（返回纯文本）或
`parse_document`（保留表格结构），文件以 base64 传入。

大材料请显式传 `max_length` 限制长度。

## 对话附件用引用读，不要 base64

用户消息里「[已上传附件：… (attachment_id=…)]」的文件已存在服务端：
用 `read_agent_attachment(attachment_id)` 直接读正文（PDF/Word 均可；
truncated=true 时用 start 分段续读）。图片附件与无文字层的扫描件会返回
**原件页图**（非 OCR——多模态视觉通道，版式/表格比 OCR 更忠实），需要指定
页时传 pages（如 `"1-3,5"` 或 `"all"`），单次最多 10 页。

## 扫描件返回 no_text_layer 时，不要装作读到了

`extract_document_text` / `parse_document` 对无文字层的扫描件会返回
`success=true` + 空 `text` + `metadata.no_text_layer=true` + `notice`——
这不是「文档内容为空」，是**提取不到文字层**：

- 对话附件：改用 `read_agent_attachment(attachment_id, pages=…)` 拿页面原图；
- 归档材料（base64 传入）：如实告知用户该材料无文字层，无法提取文本，
  不要基于「空」下任何结论。

## 长文档可能转异步

长文档解析可能转异步，此时返回 `task_id`，用 `get_document_parsing_task`
轮询——不要在原地反复重发解析请求。
