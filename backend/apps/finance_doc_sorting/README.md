# 🗂️ 案件材料整理（evidence_sorting）

案件财务材料整理工具：图片 OCR 关键词分类（对账单 / 出库单 / 收款凭证 / 其他）+ LLM 解析对账单 + 交叉比对 + 按月归档导出 ZIP。

## 功能概述

- 前端上传 base64 图片，服务端 OCR（复用 image_rotation 的方向检测 + 文本）后按关键词权重表分类，并正则提取日期（YYYYMMDD）与金额（取最大值）、对账单签名关键词检测
- LLM（可指定 backend/model）把对账单 OCR 文本解析为结构化 JSON（月份 / 总额 / 签名 / 逐笔明细）
- 交叉比对：对账单明细 ↔ 出库单按日期 + 金额匹配（1% 容差），按月分组并生成带状态标注的文件夹名（已确认 / 对账单未签名 / 缺少出库单 / 出库单数量不够 / 不匹配 / 需补充）
- 导出 ZIP：月份文件夹（对账单 + 按日期排序出库单，文件名含金额 / 签名 / 序号 / 备注）+ 未签名 / 收款情况 / 其他 / 未匹配出库单，落盘 `MEDIA_ROOT/evidence_sorting/` 返回下载 URL
- `/llm-options` 探测可用 LLM 后端与模型列表

## 目录结构

```
evidence_sorting/
├── apps.py
├── models/base.py                     # EvidenceSorting 虚拟模型
├── api/evidence_sorting_api.py        # 5 个端点（export/llm-options 有限流）
├── schemas.py
├── services/
│   ├── classifier.py                  # 同步/异步并发 OCR + 分类
│   ├── reconciler.py                  # LLM 对账单解析 + 比对算法 + 文件夹命名
│   └── exporter.py                    # ZIP 组装与命名
├── admin/evidence_sorting_admin.py    # 工具页入口
└── templates/admin/evidence_sorting/evidence_sorting.html
```

## 数据模型

- `EvidenceSorting` — managed=False 虚拟模型（不建表），仅作 Admin 菜单入口

## API 端点

前缀 `/api/v1/evidence-sorting`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/classify` | 批量图片 OCR + 关键词分类 |
| POST | `/parse-statement` | LLM 解析对账单 OCR 文本 |
| POST | `/reconcile` | 对账单 × 出库单交叉比对 |
| POST | `/export` | 比对 + 归档 ZIP 导出（限流 EXPORT） |
| GET | `/llm-options` | 可用 LLM 后端 / 模型（限流 LLM） |

## Admin

`EvidenceSortingAdmin` — 挂在虚拟模型上的只读工具页入口（禁止增删改）。

## 设计要点

- **无状态设计**：所有数据由前端在请求间持有（base64 图片 + OCR 结果回传），服务端不落库，仅导出时写 ZIP 文件
- 分类完全基于关键词计数（OCR 无文字的 PNG 兜底判为对账单截图）
- 金额匹配容差 max(1%, 1 元)；仅日期匹配也可算命中
- 文件夹命名即比对结论：`2022年08月对账单与出库单（已确认/对账单未签名_...）`

## 外部集成

- OCR 复用 `apps.image_rotation.services.orientation.service.OrientationDetectionService`
- LLM 走 `apps.core.llm.get_llm_service()`（支持 backend/model 覆盖与 fallback）

## 依赖模块

- `apps.core`（认证、限流、llm、路径工具）、`apps.image_rotation`（动态 import）
