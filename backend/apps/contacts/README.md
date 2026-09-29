# 👔 工作人员联系方式（contacts）

案件工作人员（法官、书记员、对方律师等）联系方式的 CRUD 与跨案件检索。

## 功能概述

- 按案件维护联系人：姓名 / 角色（ContactRole）/ 电话 / 收件地址 / 阶段（CaseStage）/ 备注 / 主管机关
- 跨案件搜索：按姓名 / 机关 / 角色聚合（出现次数 + 关联案件 id 列表 + 最新联系方式），批量查询避免 N+1
- 全部端点要求 admin 权限（DjangoPermsMixin.ensure_admin，支持 perm_open_access）
- 修改历史审计（django-simple-history）

## 目录结构

```
contacts/
├── apps.py
├── models.py                     # CaseContact（含 HistoricalRecords）
├── api/contact_api.py            # 6 个端点（全 async + sync_to_async）
├── schemas/contact_schemas.py    # CaseContactIn/Out/Update/SearchResult
├── services/contact_service.py   # CRUD + 跨案件聚合搜索
├── admin.py                      # CaseContactAdmin + Inline + 表单（机关自动补全）
└── migrations/
```

## 数据模型

- `CaseContact` — 案件工作人员联系方式（FK Case、FK SupervisingAuthority、ContactRole、CaseStage，带历史表）

## API 端点

前缀 `/api/v1/contacts`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/contacts` | 列表（可按 case_id/stage 过滤）/ 创建 |
| GET | `/contacts/search` | 跨案件搜索（q/court/role/limit） |
| GET/PUT/DELETE | `/contacts/{contact_id}` | 详情 / 更新 / 删除 |

## 设计要点

- 主管机关在表单层以名称输入（js-court-autocomplete 自动补全），clean 时对 case 级 get_or_create `SupervisingAuthority`（authority_type=court），即机关按案件隔离存储
- `CaseContactInline` 供其他 app（如 cases）内联使用

## 外部集成

无。

## 依赖模块

- `apps.cases`（Case、SupervisingAuthority）、`apps.core`（ContactRole/CaseStage 枚举、异常、权限 Mixin、SchemaMixin）、simple_history、nested_admin（可选降级）
