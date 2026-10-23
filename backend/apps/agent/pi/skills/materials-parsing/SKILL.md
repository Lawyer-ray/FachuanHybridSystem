---
name: materials-parsing
description: 读取归档材料正文、解析文档、提取表格内容的指引。当用户要「看看这份材料写了什么」「提取合同正文」「解析 PDF/表格」时使用。
---

# 材料与正文

## 归档材料的正文不在数据库里

要读某份材料的实际内容，用 `extract_document_text`（返回纯文本）或
`parse_document`（保留表格结构），文件以 base64 传入。

大材料请显式传 `max_length` 限制长度。

## 对话附件用引用读，不要 base64

用户消息里「[已上传附件：… (attachment_id=…)]」的文件已存在服务端：
用 `read_agent_attachment(attachment_id)` 直接读正文（PDF/Word/图片均可，
图片走 OCR；truncated=true 时用 start 分段续读）。

## 长文档可能转异步

长文档解析可能转异步，此时返回 `task_id`，用 `get_document_parsing_task`
轮询——不要在原地反复重发解析请求。
