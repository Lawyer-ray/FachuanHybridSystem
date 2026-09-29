# 🔁 要素式转换（doc_convert）

传统法律文书转「要素式文书」的转换工具：上传文书 + 选择文书类型（mbid），调用外部 znszj 转换系统，转换产物直接返回并落库存档（历史可重新下载）。

## 功能概述

- `GET /mbid-list` 返回支持的文书类型清单（69 个 mbid，按起诉状 / 申请书 / 答辩状等类别分组），数据来自 `constants.py` 静态清单，不受功能开关控制
- `POST /convert` 上传 .docx / .doc / .pdf（最大 20MB）+ mbid，转换后直接以附件返回 docx
- **每次转换（无论成败）落一条 `DocConvertRecord`**：成功存产物文件，失败存错误信息（截断 2000 字符）——历史弹窗可重新下载
- 历史记录分页（status 过滤）、重新下载产物、删除记录（信号清理物理文件）
- 转换能力来自外部 znszj 系统，客户端从 `plugins.doc_convert` 插件动态加载（开源版无插件时抛 ZnszjNotConfiguredError）；需 `settings.ZNSZJJ_ENABLED=True` 否则 403

## 目录结构

```
doc_convert/
├── apps.py                       # ready() 导入 signals
├── models.py                     # DocConvertTool(虚拟) + DocConvertRecord
├── constants.py                  # MBID_DEFINITIONS 文书类型清单 + 分组工具
├── exceptions.py                 # 业务/校验异常
├── api/doc_convert_api.py        # 5 个端点
├── admin/doc_convert_tool_admin.py  # stub，从 plugins.doc_convert.admin 再导出
├── services/
│   ├── doc_convert_service.py    # 校验 + 调 znszj
│   ├── record_service.py         # 记录落库/分页/详情
│   └── znszj_loader.py           # znszj 客户端插件动态加载（带缓存）
└── signals.py                    # 记录删除清理产物文件
```

## 数据模型

- `DocConvertTool` — managed=False 虚拟模型，仅作 Admin 入口
- `DocConvertRecord` — 转换历史（original_name、mbid、mbid_name、status success/failed、error_message、output_file、created_by；索引 `(status, -created_at)`）

## API 端点

前缀 `/api/v1/doc-convert`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/mbid-list` | 文书类型分组列表 |
| POST | `/convert` | 上传转换并返回 docx |
| GET | `/records` | 历史记录分页 |
| GET | `/records/{record_id}/download` | 下载产物（仅 success 且有文件） |
| DELETE | `/records/{record_id}` | 删除记录 |

## 异步任务与信号

无异步任务；`signals.post_delete(DocConvertRecord)` 在 on_commit 后删除 output_file 物理文件。

## 外部集成

- znszj 法律文书转换系统（认证 → 上传 → 转写 → 保存取下载链接 → 下载 docx），经闭源插件 `plugins.doc_convert` 接入，开源仓库不含对接代码

## 依赖模块

- `apps.core`（upload_paths 的 DatedUUIDPath/MediaEntity、异常）；可选 `plugins`
