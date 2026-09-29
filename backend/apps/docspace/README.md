# 🗃️ DocSpace 云文档（docspace）

对接 OnlyOffice DocSpace 云文档服务：上传 / 新建 / 列表 / 下载 / 删除 / 元数据同步，本地存映射记录。

## 功能概述

- 配置从 `SystemConfig` 读取（DOCSPACE_PORTAL_URL / DOCSPACE_API_TOKEN / DOCSPACE_ROOT_FOLDER_ID，token 经 SecretCodec 解密；根文件夹未配置时自动调 `/api/2.0/files/@my` 发现）
- 上传文件或新建空白 .docx（本地 zip 生成最小 docx）；`GET /config` 返回 portal_url + enabled
- 本地 `DocSpaceDocument` 按 `docspace_file_id` 唯一映射，get_or_create 并补丁更新 web_url（DocSpace 对相同内容去重）
- 文档列表限本人（lawyer=request.auth）最近 50 条；删除时先删远端（容忍失败）再删本地；sync 端点拉取远端元数据刷新本地并记录 last_editor

## 目录结构

```
docspace/
├── apps.py
├── models/document.py            # DocSpaceDocument
├── schemas.py / config.py        # 配置读取 + 根目录发现 + is_configured
├── api/docspace_api.py           # 7 个端点（全 async）
├── admin/document_admin.py
└── services/docspace_client.py   # DocSpaceClient（httpx 同步+异步双套）
```

## 数据模型

- `DocSpaceDocument` — lawyer FK（CASCADE）、title、docspace_file_id（unique）、docspace_folder_id、file_ext、content_length、web_url、last_editor（SET_NULL）；索引 `(lawyer, -updated_at)`

## API 端点

前缀 `/api/v1/docspace`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config` | 配置与启用状态 |
| POST | `/upload` | 上传文件（可选 folder_id） |
| POST | `/create` | 新建空白 docx |
| GET | `/documents`、`/documents/{doc_id}` | 当前用户文档列表 / 详情 |
| DELETE | `/documents/{doc_id}` | 删除（远端 + 本地） |
| GET | `/documents/{doc_id}/download` | 代理下载远端文件 |
| POST | `/sync/{doc_id}` | 刷新文档元数据 |

## Admin

`DocSpaceDocumentAdmin`（基础 list_display）。

## 设计要点

- 全异步视图（async + aget/asave）；远端删除失败仅 warning 不阻断本地删除
- 数据迁移 0002 预置空配置键（敏感值不进代码）；`settings.DOCSPACE_ENABLED` 开关默认关闭

## 外部集成

OnlyOffice DocSpace REST API v2.0（httpx，30s 超时 / 10s 连接超时）。

## 依赖模块

- `apps.core`（SystemConfig、SecretCodec、JWTOrSessionAuth）、`apps.organization`（Lawyer）
