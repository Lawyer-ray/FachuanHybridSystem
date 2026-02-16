# ⏰ 重要日期提醒模块 (Reminders)

Reminders 模块负责维护案件相关的关键日期提醒（到期时间、提醒策略、状态流转），并提供 Admin 与 API 的统一入口。

## 📚 模块概述

本模块提供：
- 提醒事项的 CRUD 与查询
- 到期时间/状态管理（到期、已完成、已取消等）
- 面向其他模块的标准化服务适配器（adapter）

## 📁 目录结构（简要）

```
reminders/
├── api/        # Ninja API
├── admin/      # Django Admin
├── services/   # reminder_service + adapter
├── models.py   # Reminder 相关模型
└── schemas.py  # API/服务层 DTO schema
```

## 🔑 核心入口

- API：`api/reminder_api.py`
- 服务：`services/reminder_service.py`、`services/reminder_service_adapter.py`
- Admin：`admin/reminder_admin.py`

