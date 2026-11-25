"""回传件内容核对（doc_verify）：判断客户回传的文书正文是否被改动。

设计口径见 `docs/analysis/doc-verify-2026-11-25/plan.md`（本地文档，不入库）：
把「文档比对」降维成「断言回归」——出站件固化成断言集，入站件逐级核对，
产出可复核的失败清单，而不是一个「改了没改」的布尔值。

分层：
- `domain/`  纯函数：归一化、断言模型、比对（无 IO、无 Django）
- `services/` 基线捕获、入站核对编排、闸门、通知
- `api/`     Ninja 路由（前缀 `/api/v1/doc-verify`）
- `models/`  出站件、核对运行、发现项、裁决（裁决 append-only）
"""
