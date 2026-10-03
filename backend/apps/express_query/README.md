# 📦 快递查询（express_query）

上传邮单图片 / PDF（OCR 识别运单号）或手动输入运单号，用**有头 Playwright 浏览器**访问顺丰 / EMS 官网（需人工扫码登录）查询物流，并把结果页面存为带时间戳页眉的 PDF。

## 功能概述

- OCR 运单号提取：SF（SF + 10~20 位数字）与 EMS（13 位纯数字）正则；PDF 邮单仅取第一页 220DPI 转图识别，识别后把原 PDF 截断为第一页节省存储
- 手动输入模式：Admin 内正则校验单号格式后跳过 OCR 直接查询
- 浏览器查询：`CloakBrowser`（`apps.core.services.browser.create_browser_async`，headless=False）复用 BrowserContext；SF 流程含登录检测与等待；EMS 流程处理协议勾选、扫码等待后进入查询页
- 查询完成后注入「日期时间 + URL」固定页眉，`page.pdf` 输出 A4 PDF
- 状态机 pending → ocr_parsing → waiting_login → querying → success/failed 全程落库
- Django-Q worker 中用 asyncio.run 执行协程，finally 主动断开 Playwright 避免 "Event loop is closed"

## 目录结构

```
express_query/
├── apps.py / api.py               # api 为单文件（任务列表端点）
├── models.py                      # Tool + Task 模型
├── admin/express_query_task_admin.py  # Tool 工作台 + Task Admin
├── services/
│   ├── tracking_extraction_service.py  # OCR + 正则 + PDF 截断
│   └── browser_query/
│       ├── service.py             # ExpressBrowserQueryService facade
│       ├── browser_launcher.py    # CloakBrowser 启动/复用/关闭
│       ├── sf_query_handler.py    # 顺丰全流程
│       ├── ems_query_handler.py / ems_auth_handler.py  # EMS 查询与登录弹窗处理
│       └── browser_utils.py       # click_first/fill_first 等工具
├── tasks.py                       # OCR / 手动两个任务入口 + _execute_browser_query
├── signals.py                     # post_delete 清理邮单与结果 PDF
└── templates/admin/express_query/workbench.html
```

## 数据模型

- `ExpressQueryTool` — managed=False 虚拟模型（verbose「查询EMS/顺丰」），Admin 工作台入口
- `ExpressQueryTask` — 查询任务（邮单文件、承运商、运单号、OCR 文本、query_url、result_pdf、result_payload、queue_task_id）

## API 端点

前缀 `/api/v1/express-query`，仅一个只读端点（主要交互在 Admin 工作台）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks` | 最近 200 条任务列表（管理员/超管全量，普通用户仅本人创建） |

## Admin

- `ExpressQueryTool` changelist 即工作台：GET 渲染、POST 分流手动输入 / 文件上传（正则校验后入队）
- `ExpressQueryTask` 全只读详情（邮单 / PDF / URL 链接、OCR 文本、彩色状态）

## 异步任务与信号

- `execute_express_query_task`（OCR 流程）、`execute_manual_express_query_task`（手动流程）
- `signals.post_delete(ExpressQueryTask)`：清理邮单与结果 PDF 物理文件

## 外部集成

- Playwright async（有头浏览器访问 sf-express.com 与 11183.com.cn）+ CloakBrowser 反检测
- OCR 经 ServiceLocator；PyMuPDF（PDF 首页转图 / 截断）

## 注意事项

- **必须人工扫码登录**：浏览器以有头模式弹出，任务进入 `waiting_login` 等待
- EMS 页面 XPath 硬编码（与测试脚本保持一致），站点改版需同步维护
- 结果 PDF 经 default_storage 存 media 相对路径 `express_query/results/{task_id}/{uuid 前缀}_{运单号}.pdf`（文件名不可预测）

## 依赖模块

- `apps.core`（upload_paths、ServiceLocator、create_browser_async、tasking）
