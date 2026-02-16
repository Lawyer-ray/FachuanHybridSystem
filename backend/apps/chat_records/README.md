# 💬 聊天记录梳理模块 (Chat Records)

Chat Records 模块用于管理聊天记录梳理任务：录屏/截图的采集、帧抽取与筛选、OCR/内容提取、结构化存储，以及导出任务的编排与交付。

## 📚 模块概述

本模块提供：
- Project/Recording/Screenshot 等数据模型，用于组织与追踪梳理任务
- 录屏帧抽取、关键帧选择、去重阈值控制等处理流程
- 导出任务（export task）与导出服务（export service）
- Admin 工作台页面（workbench）用于人工复核与操作

## 📁 目录结构（简要）

```
chat_records/
├── api/        # Ninja API
├── admin/      # Django Admin
├── models/     # project/recording/screenshot/export_task 等
├── services/   # 抽帧、筛选、提取、导出与任务编排
├── templates/  # admin 工作台页面
└── static/     # workbench 前端资源
```

## 🔑 核心入口

- API：`api/chat_records_api.py`
- 服务：`services/recording_service.py`、`services/recording_extract_facade.py`、`services/export_service.py`
- Admin：`admin/chat_record_admin.py`、`templates/admin/chat_records/workbench.html`

