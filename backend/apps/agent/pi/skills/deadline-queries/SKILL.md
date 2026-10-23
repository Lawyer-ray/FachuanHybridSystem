---
name: deadline-queries
description: 期限、排期、开庭、到期事项与异步任务进度的查询指引。当用户问「未来 N 天有什么到期」「明天有开庭吗」「这个月排期」「某个异步任务好了吗」时使用。
---

# 期限与进度查询

## 跨对象期限汇总

问「未来 N 天有什么到期事项」「明天有开庭吗」时，用
`list_upcoming_deadlines(days=N)`——它跨案件、合同、案件日志统一汇总并按
到期时间排序。**不要**用 `list_all_reminders` 逐个目标去拼，那样必然漏项。

问「这个月排期」时用 `get_reminder_calendar`（后端已对重复庭审去重）。

## 异步任务进度

问「某个异步任务好了吗」（PDF 拆页 / OA 归档 / 盖章 / 文书生成）时，用
`get_async_task_status(kind, task_id)`，一次拿统一字段，不要凭记忆猜状态名。
