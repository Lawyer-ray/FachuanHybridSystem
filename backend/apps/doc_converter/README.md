# 📄 DOC 批量转 DOCX（doc_converter）

批量 .doc → .docx 转换（LibreOffice 无头模式）：Django-Q2 异步任务 + ZIP 打包下载 + macOS 剪贴板复制 + 保存到指定目录。

## 功能概述

- 多文件上传建任务（仅 .doc，上限 `LARGE_FILE_MAX_SIZE`），事务提交后才入队（避免竞态）
- 分批（25 个/批）调 soffice 转换，实时进度（progress 封顶 99 直到完成），支持取消（区分 pending 直接标 cancelled 与运行中 kill Q2 任务）
- 产物 UUID 重命名落库，ZIP 打包时映射回原始文件名（规避中文长文件名超 DB 字段限制；下载靠响应头改名）
- **复制到剪贴板**：后端与用户同机时用 macOS NSPasteboard 写 file-url（等效 Finder ⌘C）；非 macOS 返回 unsupported。副本写在临时固定目录且不能删（file-url 是路径引用）
- **保存到指定目录**：把产物按原名复制到服务器指定目录（禁止 MEDIA_ROOT 内、禁止 `..`）
- `GET /health` 探测 LibreOffice 可用性；历史任务分页、删除任务连带清理全部文件

## 目录结构

```
doc_converter/
├── apps.py / models.py / schemas.py
├── api/doc_converter_api.py          # 9+ 端点
├── admin/doc_converter_admin.py      # Job 管理 + Tool 工作台
├── tasks.py                          # run_conversion_job（Q2 入口）
├── signals.py                        # Job/Item post_delete 文件清理
├── management/commands/cleanup_stale_doc_converter_jobs.py
├── services/
│   ├── converter_service.py          # 业务编排（建任务/取消/进度/目录保存）
│   ├── engine.py                     # convert_single / batch_convert（soffice headless）
│   └── storage.py                    # DocConverterStorage（job 目录管理）
└── templates/admin/doc_converter/workbench.html
```

## 数据模型

- `DocConverterTool` — managed=False 虚拟模型（Admin 入口）
- `DocConverterJob` — 转换任务（UUID 主键；status pending/converting/packing/completed/failed/cancelled、total/converted/failed_files、progress、cancel_requested、output_zip）
- `DocConverterItem` — 明细（original_name、source_file、converted_file、status、error、duration_ms）

## API 端点

前缀 `/api/v1/doc-converter`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST/GET | `/jobs` | 创建任务（多 .doc）/ 历史分页 |
| GET | `/jobs/{job_id}` | 进度（含 items 明细） |
| POST | `/jobs/{job_id}/cancel` | 取消 |
| GET | `/jobs/{job_id}/download` | 下载结果 ZIP |
| GET | `/jobs/{job_id}/items/{item_id}/download` | 下载单个 docx |
| POST | `/jobs/{job_id}/items/copy-to-clipboard` | macOS 剪贴板文件写入 |
| POST | `/jobs/{job_id}/save-to-dir` | 保存到服务器目录 |
| DELETE | `/jobs/{job_id}` | 删除任务及文件 |
| GET | `/health` | LibreOffice 探测 |

## Admin

`DocConverterJobAdmin`（全只读 + Item inline）；`DocConverterToolAdmin` 渲染工作台页面。

## 异步任务与信号

- `run_conversion_job`（Q2，timeout 7200）
- `cleanup_stale_doc_converter_jobs` 管理命令（`--max-age` 完成任务默认 60 分钟、`--stale-max-age` 卡住任务默认 30 分钟、`--dry-run`）
- post_delete 信号清理 Job 的 zip + 目录、Item 的源/产物文件（on_commit）

## 外部集成

LibreOffice（apps.core.services.libreoffice.find_libreoffice）；macOS AppKit NSPasteboard。

## 依赖模块

- `apps.core`（常量、任务提交、异常、storage_service、libreoffice、mac_clipboard_service）
