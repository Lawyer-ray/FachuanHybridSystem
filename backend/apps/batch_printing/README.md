# 🖨️ 批量打印（batch_printing）

把批量上传的 PDF/DOCX 按文件名关键词匹配到「打印机 + 打印预置」，在 macOS 上通过 CUPS `lp` 命令静默批量打印。**平台强绑定 macOS**（依赖 CUPS 与 Apple 打印预置 plist 格式）。

## 功能概述

- 自动发现 macOS 打印预置：解析 `~/Library/Preferences/com.apple.print.custompresets.forprinter.*.plist` 并快照入库，含 `lpoptions -l` 驱动参数校验
- 关键词路由规则：按「文件名关键词 → 打印预置」配置规则，保存时自动同步预置所属打印机；执行时按优先级匹配
- 批量上传 PDF/DOCX 创建打印任务；DOCX 经 LibreOffice headless 转 PDF 后打印
- 逐文件执行 `lp -d 打印机 -o k=v ...` 静默打印，记录 CUPS 任务 ID；未命中任何规则的文件直接判失败
- 任务进度 / 取消（进度与取消检查每 10 项批量刷新，减少 DB 写入）；部分失败终态为 `partial_failed`
- 能力探测端点：检测本机是否安装 soffice 等依赖

## 目录结构

```
batch_printing/
├── apps.py                      # AppConfig，ready() 导入 signals
├── models.py                    # 5 个模型 + 3 组 TextChoices
├── schemas.py                   # 出入参 Schema
├── api/batch_printing_api.py    # Ninja 路由（全 async + sync_to_async）
├── admin/batch_printing_admin.py# 4 个模型 Admin + 工作台
├── services/
│   ├── wiring.py                # 手工依赖装配工厂
│   ├── storage.py               # BatchPrintStorage（MEDIA/batch_printing/jobs/{id}/...）
│   ├── execution/
│   │   ├── mac_print_executor_service.py  # lp 命令执行器
│   │   └── rule_service.py                # 规则 CRUD + 按优先级匹配
│   ├── job/
│   │   ├── file_prepare_service.py        # PDF 拷贝 / DOCX→PDF
│   │   └── job_service.py                 # 任务创建/列表/取消/执行主循环
│   └── preset/
│       ├── preset_discovery_service.py    # plist 解析 + 快照入库
│       └── preset_service.py              # 预置查询与 payload 构建
├── tasks.py                     # execute_batch_print_job 任务入口
├── signals.py                   # post_delete 清理任务目录
└── templates/admin/batch_printing/workbench.html
```

## 数据模型

- `BatchPrintingTool` — managed=False 虚拟模型，仅作 Admin 工作台入口
- `PrintPresetSnapshot` — 打印预置快照（打印机、预置名、选项 payload）
- `PrintKeywordRule` — 关键词打印规则（关键词 → 预置，含优先级）
- `BatchPrintJob` — 批量打印任务（UUID 主键，状态机、进度、统计）
- `BatchPrintItem` — 批量打印明细（order 唯一约束、每文件结果与 CUPS 任务 ID）

## API 端点

前缀 `/api/v1/batch-printing`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/capabilities` | 能力探测（soffice 等） |
| GET | `/presets`、`/presets/{id}` | 预置列表 / 详情 |
| POST | `/presets/sync` | 同步本机打印预置快照 |
| GET/POST | `/rules`、GET/PUT/DELETE `/rules/{id}` | 关键词规则 CRUD |
| GET/POST | `/jobs`、GET/DELETE `/jobs/{job_id}` | 任务创建 / 列表 / 详情 / 删除 |
| POST | `/jobs/{job_id}/cancel` | 取消任务 |

## Admin

- `BatchPrintingTool` 的 changelist 直接渲染自定义工作台页面（上传与规则配置入口）
- `PrintKeywordRule` 用自定义 ModelForm（只选预置，打印机自动带出）
- `BatchPrintJob` 全只读 + 明细 Inline + 彩色状态列

## 异步任务与信号

- `tasks.execute_batch_print_job`：经 core 任务提交服务派发到 Django-Q 执行，异常落库 FAILED
- `signals.post_delete(BatchPrintJob)`：`transaction.on_commit` 后清理任务文件目录

## 外部集成

- macOS `lp` / `lpoptions` 子进程（CUPS 打印）
- LibreOffice soffice headless（DOCX → PDF，经 `apps.core.services.libreoffice`）
- 读取用户 `~/Library/Preferences` 打印预置 plist

## 依赖模块

- `apps.core`：异常体系、`LARGE_FILE_MAX_SIZE`、任务提交服务、storage_service
