# ⏰ 重要日期提醒模块 (Reminders)

管理案件/合同相关的关键日期提醒（开庭、举证到期、上诉期等）。

## 📁 目录结构

```
reminders/
├── api/        # Ninja API（CRUD + 类型枚举）
├── admin/      # Django Admin
├── ports/      # 目标查询端口（Contract/CaseLog）
├── services/   # ReminderService（业务逻辑）+ Adapter（跨模块接口）
├── models.py   # Reminder 模型
└── schemas.py  # API 输入/输出 Schema
```

## 🔑 核心设计

- `Reminder` 必须绑定 `contract` 或 `case_log` 之一（DB 级 CheckConstraint）
- `ReminderService` 通过构造注入 `ContractTargetQueryPort` / `CaseLogTargetQueryPort`，不直接依赖外部模块 Model
- `ReminderServiceAdapter` 实现 `IReminderService` 协议，供案件模块、合同模块、自动化模块调用
- 文书类型到提醒类型的映射在 Adapter 的 `DOCUMENT_TYPE_TO_REMINDER_TYPE` 中维护
- 读侧导出能力（合同/案件日志/批量/最新一条）统一由 Adapter 提供，消费侧不直接使用 reverse ORM 作为主路径

## 🔌 对外能力（IReminderService）

- 创建：`create_case_log_reminder_internal` / `create_contract_reminders_internal` / `create_case_log_reminders_internal`
- 查询：`export_contract_reminders_internal` / `export_case_log_reminders_internal` / `export_case_log_reminders_batch_internal`
- 摘要：`get_latest_case_log_reminder_internal`
