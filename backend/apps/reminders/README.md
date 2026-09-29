# ⏰ 重要日期提醒（reminders）

提醒 CRUD + 自然语言解析创建 + 月历视图 + 完成态管理 + ICS 日历订阅 + 本地日历（macOS / Windows / ICS 文件 / ICS URL）同步导入。

## 功能概述

- 提醒 CRUD（8 种 ReminderType）+ `POST /parse` 自然语言解析创建（「下周三上午十点开庭」等）
- **绑定规则**：contract / case / case_log **至多绑一个、允许全空**（独立提醒，供文书识别「记一笔」等场景，DB 级 CheckConstraint）
- 月历视图（`/calendar`）+ Admin 完整日历工作台（11 个自定义 URL）
- 完成态：`POST /complete`、is_completed / completed_at / completed_by（日历勾选完成）
- ICS 订阅：CalendarFeedToken（用户专属令牌）+ 3 个 feed 端点，ICS 子路由免登录 token 鉴权
- 本地日历同步导入：四 provider（macOS / Windows / ICS 文件 / ICS URL），预览 + 去重 + 导入
- simple_history 历史记录；`include_in_important_time` 同步案件详情重要时间展示

## 目录结构

```
reminders/
├── models.py               # Reminder（8 种类型）+ CalendarFeedToken
├── api/                    # CRUD + parse + calendar + complete + ics feed
├── services/               # ReminderService、ReminderServiceAdapter、reminder_parser_service、
│                           #   validators、calendar_export/calendar_month/calendar_sync/calendar_view
│                           #   + calendar_providers/（ics/ics_url/mac/windows）
├── ports/                  # ContractTargetQueryPort / CaseLogTargetQueryPort / CaseTargetQueryPort
└── admin/                  # SimpleHistoryAdmin + 日历工作台（11 个自定义 URL）+ 2 个模板
```

## 数据模型

- `Reminder` — 提醒（类型、目标至多绑一、metadata、include_in_important_time、完成态、HistoricalRecords）
- `CalendarFeedToken` — 用户专属 ICS 订阅令牌（token_urlsafe(48)）

## API 端点

前缀 `/api/v1/reminders`（JWT+Session 双认证；ICS 子路由免登录 token 鉴权）：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/parse` | 自然语言解析创建 |
| GET | `/list`、`/types`、`/target-options`、`/calendar` | 列表 / 枚举 / 月历 |
| POST | `/create`、`/complete` | 创建 / 完成 |
| GET/PUT/DELETE | `/{reminder_id}` | 详情 / 更新 / 删除 |
| GET | `/ics/feed`、`/ics/feed/token` | ICS 订阅 / 令牌 |
| POST | `/ics/feed/token/regenerate` | 重置令牌 |

## 对外能力（IReminderService，ReminderServiceAdapter）

- 创建：`create_case_log_reminder_internal` / `create_contract_reminders_internal` / `create_case_log_reminders_internal` / `create_reminder_internal` / `upsert_case_log_reminder_internal` / `clear_case_log_reminder_internal`
- 查询：`export_contract_reminders_internal` / `export_case_log_reminders_internal` / `export_case_log_reminders_batch_internal`
- 摘要：`get_latest_case_log_reminder_internal` / `get_reminder_type_by_code_internal` / `get_reminder_type_for_document_internal` / `get_existing_reminder_times_internal`

消费侧不直接使用 reverse ORM 作为主路径；文书类型到提醒类型的映射在 Adapter 的 `DOCUMENT_TYPE_TO_REMINDER_TYPE` 维护。
