<h1 align="center">法穿SI Copilot</h1>

<p align="center">
  <strong>一线执业律师主导研发的法律事务管理系统</strong><br>
  <sub>开源 · 私有化部署 · 数据自持 · 不是 Demo，是 7×24 跑在生产环境的那一套</sub>
</p>

<p align="center">
  <a href="https://github.com/Lawyer-ray/FachuanHybridSystem/actions"><img src="https://img.shields.io/github/actions/workflow/status/Lawyer-ray/FachuanHybridSystem/backend-ci.yml?label=Backend%20CI" alt="Backend CI"></a>
  <a href="https://github.com/Lawyer-ray/FachuanHybridSystem/actions"><img src="https://img.shields.io/github/actions/workflow/status/Lawyer-ray/FachuanHybridSystem/frontend-ci.yml?label=Frontend%20CI" alt="Frontend CI"></a>
  <a href="https://github.com/Lawyer-ray/FachuanHybridSystem/stargazers"><img src="https://img.shields.io/github/stars/Lawyer-ray/FachuanHybridSystem?style=social" alt="Stars"></a>
</p>

<p align="center">
  <code>36</code> 个业务模块 · <code>177</code> 个模型 · <code>647</code> 个 API 端点 · <code>423</code> 个 MCP 工具<br>
  <sub>统计口径见 <a href="#-规模与口径">文末</a>，命令可自行复核</sub>
</p>

---

## 30 秒了解

律师的日常被切成三段互不相通的工作：**收材料 → 办案件 → 归档**。同一份信息要在律所 OA、法院诉讼服务网（即「一张网」，法院官方的在线诉讼服务平台）、自己的文件夹里各录一遍。这个系统把它们接成一条线，并按**诉讼 / 非诉**两条主线分别组织——同一个项目详情页，左栏是按 `case_type` 自动分流的。

```
                 ┌───────────────────────────────────────┐
  材料从哪来      │  React 19 SPA  (Vite, :5090)           │
  ├ 法院短信      │ 预处理 · 项目 · 立案 · Copilot · 设置    │
  ├ 客户上传链接   └──────┬────────────────────┬────────────┘
  ├ 邮箱 / 企微      REST │                    │ SSE
  └ 本地扫描件           ▼                    ▼
                 ┌────────────────┐  ┌─────────────────────┐
                 │ Django Ninja   │  │ agent (pi runtime)  │
                 │ 647 端点       │  │ 进程池 + 四级审批     │
                 │ 36 app/177 模型 │  └──────────┬──────────┘
                 └───────┬────────┘             │ MCP (http)
                         │                      ▼
           ┌─────────────┴───────┐  ┌────────────────────┐
           │ PostgreSQL · Valkey │  │ 共享 MCP :8011     │
           │ Django-Q2·Channels  │  │ 423 工具，一份常驻  │
           └─────────────────────┘  └────────────────────┘
```

---

## 两条主线：诉讼与非诉

系统只按一件事切第一刀：**这个委托要不要打官司**。合同/案件的 `case_type` 决定一切——
`civil` / `criminal` / `administrative` / `labor` / `intl` 走**诉讼线**，`special` / `advisor` 走**非诉线**。
同一个项目详情页（`/projects/:id`），左栏按这个判定分流：诉讼看到案件程序链，非诉看到合同文件夹。

```
诉讼线                                    非诉线
─────────                                ─────────
材料预处理（收件箱→待处理→已归案）          合同生成（结构化数据 + 规则）
        ↓                                        ↓
建案 / 归入既有案件                         合同审查（OnlyOffice + AI 条款建议）
        ↓                                        ↓
案件程序链（18 种阶段）                  专项：阶段树 + 交付物表格
        ↓                                  常法：按日流水推进
立案（律所 OA / 一张网）
        ↓
归档（封面 + 登记表 + 卷内目录 + 合并 PDF）
```

### 诉讼线

**材料预处理**是诉讼线的入口，也是系统的主干。一级导航就是这条漏斗的四个阶段——顺序即漏斗顺序：

```
收件箱  →  待处理  →  已归案  →  不接归档
```

- **收件箱**：法院送达短信、客户上传链接、IMAP 邮箱、IM 群消息汇聚到一处
- **待处理**：整包 PDF 自动分段识别（起诉状 / 证据清单 / 借款合同 / 判决书 / 执行申请书…共 29 类），逐块可信度复核，识别不准的当场改
- **已归案**：一键建案或并入既有案件，材料自动落进案件文件夹
- **不接归档**：明确标记"不要"，避免每次都要重新判断

> 设计取舍：不追求全自动。拆包后的分类结果带着**置信度**送到律师面前，人工确认一次，比追求 100% 自动更务实——错一次的成本远高于点一下鼠标。

**银行批量诉讼**是诉讼线里最深的一条端到端路径，按律师实际推进顺序排成七个分区：

```
整包分段 → 起诉条件 → 要素式转换 → OA 立案 → 一张网立案 → OA 盖章 → OA 归档
```

> **⚠️ 本系统不提供自动立案。**
>
> 「一张网」即法院诉讼服务网（人民法院在线服务）。系统只做到立案前的准备——要素式转换、起诉条件校验、材料齐备度检查——提交与审核由律师本人完成。

一份信贷档案动辄 30 页混装扫描件，拆不开后面全部无从谈起。打开案件第一眼落在「整包分段」——那是律师拿到材料后的第一个动作，不是最后一个。

其余诉讼能力：18 种阶段（一/二审、执行、侦查、审查起诉、再审、申诉抗诉…）、案件链追溯（一审→二审→再审→执行）、收款跟踪、重要日期提醒、诉讼费核对、LPR 分段计息。

### 非诉线

非诉没有"程序链"，只有合同本身，所以这一线围绕合同展开：

- **生成**：合同、当事人、收费模式（固定 / 半风险 / 全风险）、代理阶段、案件关联全部结构化建模。一个委托合同下挂三个借贷案、不同律师代理不同案件、各自收费模式不同——这类逻辑用占位符表达不了，所以走数据模型 + 规则生成
- **审查**：合同复审工作台，OnlyOffice 画布 + AI 条款建议，改完可直接「另存为」保留原件
- **专项**（`special`）：按合同约定的阶段交付（尽调 → 方案 → 起草 → 登记 → 交割），每阶段树 + 交付物表格
- **常法**（`advisor`）：按"哪天做了什么"推进，事项天然散落成流水——两种推进方式在详情页是两个不同的左栏，不混在一起

## AI：能操作整个系统，而不只是聊天

Copilot 横跨两条主线，差异化在这里：AI 不是侧边栏，是**能操作整个系统的人**。

| 关键决策 | 做法与理由 |
|:---|:---|
| **运行时** | 建在 [pi](https://github.com/earendil-works/pi-coding-agent) 上，独立于业务 app。审批状态落库可审计，会话状态纯净，进程池并发 |
| **工具面** | 423 个 MCP 工具**一份常驻进程**共享（:8011）。8 并发实测 3.4s / 71MB；若每进程各起一份 stdio 则 4.1s / 1.8GB，且每路首响应等 6 秒冷启动 |
| **权限** | 工具调用前可阻塞等人工审批，分四级（低/中/高/紧急）；无人在线时高危工具挂起等离线审批 |
| **身份** | 工具以**当前律师本人身份**调 REST，归属过滤、权限、审计与本人登录完全一致（修 confused deputy） |
| **工具面收紧** | pi 只被声明 `mcp__fachuan__*`，内置 `read`/`bash`/`edit`/`write` 一律不给——它们能以 Django 进程权限读写文件、执行命令，是提示注入直通服务器 RCE 的通道 |
| **失败关闭** | 审批扩展缺失时进程拒绝启动（fail-closed），而不是静默降级放行 |

多模型可切换（OpenAI 兼容端点 / 本地模型），流式输出、工具调用可视化、运行中插话（steer）、任务式后台执行（入队 Django-Q 复用同一条流式链路）。

更多能力：PDF 拆解 · OCR 逐页分类 · 聊天记录录屏取证 · 要素式文书转换（40+ 种） · 案例检索 · 企业信息查询 · 快递轨迹 · LPR 分段计息 · 诉讼费核对 · OA 归档 · 批量打印。

---

## 技术栈

| 层级 | 技术 |
|:---|:---|
| **前端** | React 19 · TypeScript 6 · Vite 8 · Tailwind CSS 4 · shadcn/ui · TanStack Query · Zustand |
| **后端** | Django 6.1 · Django Ninja 1.7 · Django-Q2 · Channels (ASGI) |
| **数据** | PostgreSQL 16 · Valkey 8（缓存 / Channel Layer） |
| **Agent** | pi runtime · FastMCP（streamable-http） · OpenAI 兼容协议 |
| **文档** | PyMuPDF · pdfplumber · pikepdf · python-docx · docxtpl · reportlab · openpyxl |
| **部署** | Docker Compose · nginx + gunicorn · launchd / systemd · 私有化 · 数据自持 |

## 项目结构

```text
FachuanHybridSystem/
├── backend/
│   ├── apps/            36 个业务模块（cases / contracts / documents / agent / …）
│   ├── mcp_server/      MCP 工具面（423 个工具，server.py 统一注册）
│   ├── apiSystem/       Django 配置与路由装配
│   ├── tests/           1411 个测试文件（unit / integration / property / structure）
│   └── plugins/         git 子模块（FachuanPlugins）
├── frontend/src/
│   ├── app/             路由表 · 路径常量 · 壳层（唯一权威，禁止手拼路径）
│   └── features/        11 个 feature（material-prep / bank-litigation / copilot / …）
├── skills/              独立可跑的 Python 技能（案件处理 / 合同处理 / 自媒体运营）
├── ml-training/         方向分类模型训练（PyTorch → ONNX）
├── deploy/              公网栈（nginx + gunicorn + Cloudflare Tunnel）
├── docs/harness/        工程规范细则（按需加载的 14 个叶子文件）
└── changelog/           546 篇版本变更记录
```

## 快速开始

完整步骤见 **[安装与部署指南](INSTALL.md)**。常用命令（根目录 `Makefile`）：

```bash
make backend        # 后端 uvicorn 热重载，:8002
make frontend       # 前端 Vite 热重载，:5090
make q              # Django-Q 任务队列（文件变化自动重启）
make mcp            # 重启共享 MCP + 工具面核对
make ci             # 本地 CI（ruff + mypy + tsc + eslint + build + bandit + pip-audit）
make ci-full        # 完整 CI（需 PostgreSQL：+ pytest + 覆盖率）
```

## 规模与口径

| 指标 | 数值 | 复核命令 |
|:---|:---|:---|
| 业务模块 | 36 | `sed -n '64,145p' backend/apiSystem/apiSystem/settings.py \| rg -o '"apps\.[a-z_]+' \| sort -u \| wc -l` |
| 数据模型 | 177 | `django.apps.get_app_configs()` 遍历 `get_models()` 求和 |
| API 端点 | 647 | `apiSystem.api.api._get_urls()`（不含 openapi/docs） |
| MCP 工具 | 423 | 导入 `mcp_server.server`，`len(mcp._tool_manager.list_tools())` |
| 数据库迁移 | 396 | `find backend/apps -path '*/migrations/*.py' ! -name '__init__.py' \| wc -l` |
| 测试文件 | 1411 / 219 | 后端 `find backend/tests -name 'test_*.py'`；前端 `find frontend/src -name '*.test.ts*'` |

> 数字会随版本增长。以上为 2026-10-31 / v27.13.11 时点。

---

## 部署方式

代码**免费开源**（非商业许可 + ≤10 人机构免费商用例外，见[许可证](#许可证)），你可以自行下载、自行部署，功能与付费部署完全一致。详见 **[INSTALL.md](INSTALL.md)**。

不想折腾环境（依赖版本、模型接通、数据库迁移、法院平台对接）的，作者提供**一对一定制部署服务**：

- 作者亲自远程部署，边部署边讲解，交付即可投入使用
- **每台机器 2000 元** · 一次性专业服务费（**不是**软件授权费、不是订阅）
- 支持 Windows / Linux / macOS（**推荐 macOS**，与开发环境一致）

这笔费用买的不是代码，是**踩过的坑和时间**：环境准备、依赖排障、版本匹配、模型/数据库/邮件/法院平台接通、历史数据迁移、上线验收，以及一对一人工答疑。自己动手完全可行，`INSTALL.md` 写全了；付费只是给「希望有人对结果负责」的人准备的可选项。

收入全部投入两件事：项目持续迭代，以及一套给中小律所的**免费律所 OA**（全国超 95% 的中小律所没有自己的 OA）。

需要部署服务，可通过公众号「法穿」联系作者。

## 支持项目

<table>
<tr>
<td align="center">
  <strong>微信赞赏</strong><br>
  <img src="backend/apps/core/static/core/images/赞赏码.png" width="120">
</td>
<td align="center">
  <strong>关注公众号</strong><br>
  <img src="backend/apps/core/static/core/images/法穿公众号.jpg" width="120">
</td>
</tr>
</table>

**加密货币捐赠**

| 币种 | 地址 |
|:---|:---|
| USDT (TRC20) | `TYs89x2uz1Qf7vALBboKcSFsZiP3J5T4h2` |
| 比特币 | `bc1p39an4kulcgl8celc23zd6yjv3j29uctgkt7szaxlljwjlfsq6eqll7kk8` |

贡献方式与致谢名单见 **[CONTRIBUTING.md](CONTRIBUTING.md)**。

## 许可证

本项目使用 **[PolyForm Noncommercial 1.0.0](LICENSE)**——非商业许可。

**例外**：**总人数 ≤ 10 人的法律服务机构**（含分所合并计算、含律师/助理/行政/财务/IT 全部人员）**以及独立执业律师个人**，可免费商用，无需付费、无需申请。详见 **[LICENSE-EXCEPTION.md](LICENSE-EXCEPTION.md)**。

超过 10 人的机构如需使用，请联系作者。

---

<p align="center">
  <sub>由一线执业律师主导研发 · 开源 · 私有化部署 · 数据自持</sub>
</p>
