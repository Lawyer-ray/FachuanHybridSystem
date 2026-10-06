# 🏢 OA 对接（oa_filing）

律所 OA（当前为金诚同达 IMS）对接 app：通过 HTTP 直连 + Playwright 兜底的自动化脚本完成立案、盖章、归档、开票引导、利冲预检、案号查 GUID、案件导入与客户导入。

## 功能概述

- **OA 立案**：把合同/案件数据映射为 OA 表单（category/stage/kindtype/rec_type 等），HTTP 主链路提交，失败自动回退 Playwright 全流程
- **盖章申请与归档提交**：由本地文件路径反查合同（StampLookupService → 文件夹绑定 → Contract → OA 案号），异步执行 Playwright 脚本
- **半自动模式**：open-oa / open-invoice / open-stamp / 利冲预检——脚本只负责登录 + 搜索 + 预填，浏览器保持打开留给律师手工操作
- **案号查 GUID**：按律所OA案件编号在 OA 案件管理页检索（WebForms postback 纯 HTTP 三步，只读），返回案件 GUID（keyid），供合同编辑页「查询ID」按钮自动填充律所ID；会话走磁盘缓存 cookies 优先（兼容仅扫码账号），失效回退 HTTP 账密登录
- **案件导入**：上传 Excel → Django-Q 预览匹配 → 确认后从 OA 批量抓取（HTTP 并发 + Playwright 兜底）并创建/更新 Contract/Case/Client/ContractParty
- **客户导入**：分页抓取 OA 当事人列表写入 Client，支持 limit/headless 与进度回写
- **双调度**：立案/盖章/归档/open-* 走进程内 `ThreadPoolExecutor(max_workers=2)`；两个导入走 Django-Q（timeout 可经环境变量调整）
- 凭证按 `site_name`（「金诚同达OA」）在 organization.AccountCredential 匹配（按登录用户隔离），Cookie 按 OA 账号隔离持久化

## 架构

```
oa_filing/
├── models/                     # OAConfig + 五类 Session（filing/stamp/archive/case_import/client_import）
├── api/                        # filing / stamp / archive / case_import / client_import 路由
├── schemas/
├── services/
│   ├── base_firm_adapter.py    # 6 个 runtime_checkable Protocol（律所无关接口）
│   ├── oa_firm_registry.py     # site_name → adapter 类路径注册表（importlib 动态加载）
│   ├── script_executor_service.py  # 通用调度器（session 管理+凭证查找+线程调度+友好错误翻译）
│   ├── case_import_service.py / client_import_service.py
│   ├── import_session_service.py / stamp_lookup_service.py / oa_data_models.py
│   └── oa_scripts/jtn/         # 金诚同达实现（完全自包含）
│       ├── adapter.py          # JTNAdapter：实现全部 Protocol + JTN 字段映射
│       ├── http_session.py     # 纯 HTTP 会话基建：常量出口/失效判定/缓存优先登录/客户端工厂
│       ├── auth/               # SSO 扫码 / HTTP POST 登录、Cookie 持久化与注入
│       ├── filing/ stamp/ archive/ invoice/ conflict_check/
│       ├── case_guid/          # 案号查 GUID（案件管理页搜索，纯 HTTP 只读）
│       ├── case_import/        # HTTP 优先 + Playwright 兜底 + 名称检索 + SSO 处理
│       └── client_import/
├── tasks.py                    # 5 个 Django-Q 任务入口
└── admin/                      # 三个 Session 只读 Admin
```

### 核心设计

- **Protocol 隔离 + 注册表分发**：新增律所只需 `oa_scripts/<firm>/adapter.py` 实现 Protocol 并在 `_ADAPTERS` 注册一行，调度器零改动
- **jtn/ 以外禁止 import jtn 模块**；adapter 只做薄委托，Playwright 逻辑在各功能子包的 mixin/service 中
- **HTTP 优先 / Playwright 兜底**分层（立案、案件导入、客户导入均如此），失败分类为「换链路重试」而非简单报错
- **jtn/http_session 纯 HTTP 会话基建**：headers/timeout/登录 URL 统一从 auth/constants 出口；会话失效判定小件（登录 URL / location.replace 占位页 / 账密表单 / 错误文案）；缓存 cookies 优先的会话解析（兼容仅扫码账号，如 huangsong）+ `http_login_cookies` 友好错误包装；`build_client` 客户端工厂（trust_env=False 内聚）。各纯 HTTP 链路（立案/案件导入/客户导入/案号查 GUID）共用，登录失败判定为强口径（停在登录页且带账密表单，或错误文案）
- **浏览器生命周期**：半自动模式返回 `(playwright, browser)`，adapter 存入 `_active_browser_sessions` 防 GC；`_cleanup_stale_sessions` 清理断连会话
- 导入服务先 `connections.close_all()` 再进 Playwright 事件循环，规避 Django 同步 ORM 限制

## API 端点

前缀 `/api/v1/oa-filing`、`/oa-stamp`、`/oa-archive`、`/case-import`、`/client-import`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/oa-filing/configs` | 支持的站点 + 是否有凭证 |
| POST | `/oa-filing/execute`、GET `/oa-filing/session/{id}` | 发起立案 / 会话状态 |
| POST | `/oa-stamp/lookup`、`/apply`、GET `/session/{id}` | 盖章反查 / 申请 / 状态 |
| POST | `/oa-archive/lookup`、`/apply`、`/open-oa`、`/open-invoice`、`/open-stamp` | 归档与半自动入口 |
| POST | `/case-import`、GET `/{id}`、POST `/{id}/execute`、`/{id}/batch-create` | 案件导入全流程 |
| POST | `/client-import`、GET `/{id}`、POST `/{id}/batch-create` | 客户导入 |

## 数据模型

- `OAConfig` — 凭证站点配置（历史遗留，新链路已不依赖）
- `FilingSession` / `StampSession` / `ArchiveSession` — 立案 / 盖章 / 归档执行记录（只读 Admin）
- `CaseImportSession` / `ClientImportSession` — 导入会话（phase、计数、result_data）

## 异步任务

tasks.py 提供 5 个 Django-Q 入口（客户导入、案件导入预览/执行、批量建案件/客户）；batch-create 经 Q 避免阻塞 HTTP 线程。并发度环境变量：`OA_CASE_IMPORT_SEARCH_WORKERS`、`OA_CASE_IMPORT_TASK_TIMEOUT_SECONDS`、`OA_CLIENT_IMPORT_TASK_TIMEOUT_SECONDS`。

## 外部集成

金诚同达 IMS（httpx/lxml 直连 + Playwright 反检测浏览器）、企业微信/飞连 SSO 扫码、Django-Q2

## 依赖模块

- `organization`、`contracts`、`cases`、`client`、`core`；被 contracts（OA 同步、案号查 GUID 端点）与 client（利冲预检）反向引用
