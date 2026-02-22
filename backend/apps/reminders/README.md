# ⏰ 重要日期提醒模块 (Reminders)

管理案件/合同相关的关键日期提醒（开庭、举证到期、上诉期等）。

## 📁 目录结构

```
reminders/
├── api/        # Ninja API（CRUD + 类型枚举）
├── admin/      # Django Admin
├── services/   # ReminderService（业务逻辑）+ Adapter（跨模块接口）
├── models.py   # Reminder 模型
└── schemas.py  # API 输入/输出 Schema
```

## 🔑 核心设计

- `Reminder` 必须绑定 `contract` 或 `case_log` 之一（DB 级 CheckConstraint）
- `ReminderServiceAdapter` 实现 `IReminderService` 协议，供案件模块、自动化模块调用
- 文书类型到提醒类型的映射在 Adapter 的 `DOCUMENT_TYPE_TO_REMINDER_TYPE` 中维护
