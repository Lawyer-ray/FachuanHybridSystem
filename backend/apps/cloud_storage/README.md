# ☁️ 云存储（cloud_storage）

从 core 拆分的多协议云存储 Provider 层与账号管理（本地文件系统 / WebDAV(坚果云) / OneDrive / S3 兼容 / Google Drive / Dropbox），为合同归档、案件材料扫描、文件夹绑定等模块提供统一读写抽象。

> **拆分说明**：app 从 core 拆出（表名钉死 `core_cloudstorageaccount`，迁移 0001 为 state-only），零数据迁移。

## 功能概述

- `CloudStorageProvider` 运行时可检 Protocol：list_directory / read_file / write_file / mkdir / exists / is_dir / delete_file / get_file_info / walk；WebDAV / OneDrive / Local 另有完整 async（a*）变体
- 工厂按 binding.storage_type 或账号实例构造 Provider；**账号缺失/未配置时返回 NullProvider（所有操作抛错）而非静默回落本地**
- 敏感字段（WebDAV 密码、OneDrive token、S3 secret、GDrive SA JSON、Dropbox secret/token）用 core.SecretCodec 加密落库，save() 幂等加密
- OneDrive / Dropbox OAuth2 设备码授权流：Admin 按钮发起 → device_code 落库 → 后台 daemon 线程轮询 token → 进程重启后 AppConfig.ready() 恢复轮询并清理过期 code
- 目录浏览助手（browse_helper，同步 + 异步）供 contracts/cases 的文件夹绑定 API 列目录
- `CloudFolderScanner` 把 Provider 适配成 BoundFolderScanService 期望的 Path-like 接口（递归收 PDF）

## 目录结构

```
cloud_storage/
├── apps.py              # ready() 恢复设备码轮询（migrate/test 跳过）
├── models.py            # CloudStorageAccount（六类存储凭据 + 加解密访问器）
├── protocols.py         # CloudFileInfo + CloudStorageProvider Protocol
├── factory.py           # create_provider_for_binding / create_provider_from_account
├── local.py             # LocalProvider（根目录逃逸防护）
├── null_provider.py     # NullProvider（显式失败）
├── webdav_provider.py   # WebDAVProvider（同步 requests + 异步 httpx，别名 JianguoyunProvider）
├── onedrive_provider.py # OAuthTokenManager（设备码+自动刷新）+ OneDriveProvider（MS Graph）
├── dropbox_provider.py  # Dropbox 设备码流 Provider
├── gdrive_provider.py   # GDriveProvider（service account，路径↔id 缓存，429/5xx 重试）
├── s3_provider.py       # S3Provider（boto3，前缀模拟目录）
├── exceptions.py        # CloudStorageError / CloudStorageRateLimitError
├── browse_helper.py     # 目录浏览（仅子目录，过滤隐藏目录）
├── scanner_adapter.py   # ScannedFile + CloudFolderScanner
├── api.py / urls.py     # OAuth 设备码授权的 staff POST 视图
└── admin.py             # CloudStorageAccountAdmin（授权按钮/状态列/轮询线程）
```

## 数据模型

- `CloudStorageAccount` — 云存储账号（唯一模型；`db_table="core_cloudstorageaccount"`；六类存储的全部凭据字段，敏感字段加密）

## API 端点

非 Ninja，Django staff 视图（项目 urls.py 挂 `admin/cloud-storage/`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/cloud-storage/{id}/onedrive/start-auth/`、`/complete-auth/` | OneDrive 设备码授权 |
| POST | `/admin/cloud-storage/{id}/dropbox/start-auth/`、`/complete-auth/` | Dropbox 设备码授权 |

## 设计要点

- **坚果云限速**：免费 600 请求/30 分钟（付费 1500），Provider 内置 `_RateLimiter`（默认 3.5s 最小间隔），HTTP 503 抛 `CloudStorageRateLimitError(retry_after=60)`；HEAD 对目录返回 403，判断目录应优先 `is_dir()`（走 PROPFIND）
- **设备码授权跨进程重启可恢复**：device_code/expires_at 落库，ready() 重建轮询线程（针对 runserver auto-reload 杀线程）
- LocalProvider 有路径逃逸校验（resolve 后必须 is_relative_to root）

## 外部集成

WebDAV（默认坚果云）、Microsoft Graph 设备码 OAuth、Dropbox OAuth2 设备码流、Google Drive（service account）、S3 兼容（boto3）、加密用 core SecretCodec。

## 依赖模块

- `apps.core`（SecretCodec、startup_db）
- **反向被依赖**：core（folder_binding_base、bound_folder_scan_service）、contracts、cases 的文件夹绑定与扫描
