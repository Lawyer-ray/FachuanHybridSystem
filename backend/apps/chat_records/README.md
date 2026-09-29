# 💬 聊天记录梳理（chat_records）

按项目上传录屏 / 截图，ffmpeg 抽帧去重生成截图序列，再导出 PDF / Word 证据文档。

## 功能概述

- 项目（ChatRecordProject）为根，录屏（ChatRecordRecording）与截图（ChatRecordScreenshot）挂项目下，导出任务（ChatRecordExportTask）异步生成 PDF / DOCX
- 录屏上传（默认上限 2GB，可由 SystemConfig `CHAT_RECORDS_MAX_VIDEO_SIZE_BYTES` 覆盖）、视频流式播放（Range 请求）、时长回写
- 五种抽帧策略：interval 固定间隔 / scene 画面变化 / smart 智能去重 / keyframe I 帧 / ocr 文本变化优先；支持取消与重置；抽帧前删本项目旧抽帧截图、保留手动上传
- 去重三通道：SHA-256 完全重复（上传与抽帧共用）、dHash 感知哈希（汉明距离阈值 + 滑动窗口）、像素平均差；OCR 策略用 shingles/Jaccard + SequenceMatcher 判定文本相似度
- 截图手动上传也可选去重、排序（capture_time 或手动 reorder）、标题 / 备注编辑
- 导出为 Django-Q2 异步任务，进度回写 DB；PDF 用 reportlab（A4、中文字体），DOCX 用 python-docx（表格版式、页码域）
- 全路由限流（UPLOAD / TASK / EXPORT，by_user）

## 目录结构

```
chat_records/
├── api/chat_records_api.py       # 约 20 个端点
├── admin/chat_record_admin.py    # 4 模型注册 + 项目工作台（workbench.html）
├── models/                       # project / recording / screenshot / export_task / choices
├── services/
│   ├── core/                     # access_policy、project_service、screenshot_service、protocols
│   ├── extraction/               # recording_service、recording_extract_facade、
│   │                             #   video_frame_extract_service（ffmpeg/ffprobe）、
│   │                             #   frame_selection_service（dHash/缩略图）、
│   │                             #   frame_processing_service（去重/OCR 相似度）、extract_helpers
│   └── export/                   # export_service（门面）、export_task_service、export_types、
│                                 #   pdf_export_service（reportlab）、docx_export_service
├── tasks.py + signals.py + schemas.py
└── templates/ + static/          # admin 工作台
```

## 数据模型

- `ChatRecordProject` — 项目（name / description / created_by，PROTECT）
- `ChatRecordRecording` — 录屏（video FileField、时长、extract_* 全套状态字段：strategy / 去重阈值 / OCR 阈值 / cancel / progress / 错误）
- `ChatRecordScreenshot` — 截图（image、ordering、title、note、capture_time、sha256、dhash、source=extract/upload、is_filtered）
- `ChatRecordExportTask` — 导出任务（export_type=pdf/docx、layout JSON、状态、output_file）

三个 LifecycleModel 均有 `@hook(BEFORE_UPDATE)` 文件字段变更删旧文件。

## API 端点

前缀 `/api/v1/chat-records`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/export-types`、`/export-statuses` | 枚举 |
| POST/GET | `/projects` | 项目 |
| GET/POST | `/projects/{id}/recordings`、GET/HEAD `/recordings/{id}/stream`（Range） | 录屏 |
| POST | `/recordings/{id}/extract`、`/extract/cancel`、`/extract/reset` | 抽帧 |
| GET/POST | `/projects/{id}/screenshots`、POST `.../reorder`、PATCH `/screenshots/{id}` | 截图 |
| POST/GET | `/projects/{id}/exports`、GET `/exports/{task_id}`、`/download` | 导出 |

## 异步任务与信号

- `export_chat_record_task`（导出）、`extract_recording_frames_task`（抽帧：软截止时间、CancellationToken 轮询取消、进度 0.5s 节流）
- post_delete 信号删三类模型文件 + 清理空父目录；子进程统一走白名单

## 外部集成

ffmpeg / ffprobe（SubprocessRunner 白名单）、OCR（ServiceLocator）、reportlab、python-docx、django-lifecycle

## 依赖模块

- `apps.core`（异常、限流、Range 响应、upload_paths、ServiceLocator、tasking）、`apps.organization`
