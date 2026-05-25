<h1 align="center">法穿 AI Copilot</h1>

<p align="center">
  <strong>由一线执业律师主导研发 · 开源 · 私有化部署 · 数据自持</strong>
</p>

<p align="center">
  <a href="https://github.com/Lawyer-ray/FachuanHybridSystem/actions"><img src="https://img.shields.io/github/actions/workflow/status/Lawyer-ray/FachuanHybridSystem/backend-ci.yml?label=Backend%20CI" alt="Backend CI"></a>
  <a href="https://github.com/Lawyer-ray/FachuanHybridSystem/actions"><img src="https://img.shields.io/github/actions/workflow/status/Lawyer-ray/FachuanHybridSystem/frontend-ci.yml?label=Frontend%20CI" alt="Frontend CI"></a>
  <a href="https://github.com/Lawyer-ray/FachuanHybridSystem/stargazers"><img src="https://img.shields.io/github/stars/Lawyer-ray/FachuanHybridSystem?style=social" alt="Stars"></a>
</p>

---

## 技术栈

| 层级 | 技术 |
|:---|:---|
| **前端** | React 19 + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| **后端** | Django 6 + Django Ninja + Django Q2 + Channels |
| **数据库** | PostgreSQL + Redis |
| **AI/LLM** | OpenAI API 兼容 · Ollama 本地模型 · WebSocket 流式对话 |
| **部署** | Docker · 私有化部署 · 数据自持 |

---

## 核心功能

### 📝 合同生成 · 一键同步 OA

- 根据当事人信息和案件情况，**自动生成完整委托合同文本**
- 条款、费用约定、代理权限全部基于模板智能填充
- 合同签订后**一键同步至律所内部 OA 系统**，案件编号自动关联，内外数据打通

### 🔔 法院短信 · 转发即处理

诉讼过程中法院不断发短信：立案通知、开庭传票、举证期限、判决书……

**传统做法**：打开链接 → 下载 PDF → 归档 → 更新日志 → 判断是否需要行动 → 设置提醒

**法穿 AI**：**律师只需转发短信，之后一切自动完成。**

```
iOS 快捷指令 / Android SMS Forwarder 转发短信
        ↓
智能解析案号 / 当事人 / 案件类型
        ↓
自动下载文书 PDF → 匹配已有案件
        ↓
规范重命名 → 自动归档到对应文件夹
        ↓
校验诉讼费是否异常
        ↓
飞书 / Telegram 实时通知律师
```

**7×24 小时无人值守运行。**

### 📡 信息中枢 · 永不遗漏

除了法院短信，法穿 AI 的**信息中转站**统一聚合 IMAP 邮箱和一张网收件箱的所有消息：

- 支持发件人白名单/黑名单过滤
- 重要附件按需下载预览
- **一个入口掌控全部信息动态**

### 🖥️ AI 工作台

内置 **AI 工作台**，支持多会话对话、流式输出、工具调用审批：

- **多模型切换**：自由选择 LLM 后端，支持 Ollama 本地模型和云端 API
- **上下文感知**：自动携带案件、客户、合同等业务数据作为对话上下文
- **工具调用审批**：AI 执行敏感操作前弹出审批对话框，律师确认后才执行
- **批量文档分析**：上传多个 PDF/DOCX 文件，AI 逐个分析并实时展示进度
- **会话管理**：历史会话列表、会话重命名、导出为 Markdown

### 📁 结案与归档

判决书或调解书到达后，同样通过法院短信自动处理链路完成接收、下载、归档。合同收费状态同步更新，财务数据自动结算。

随后进入归档环节，法穿 AI 提供**全流程智能归档能力**：

| 功能 | 说明 |
|:---|:---|
| 归档检查清单 | 根据合同类型自动匹配法律顾问（11项）、诉讼/仲裁（19项）、刑事（17项）三类检查清单，逐项校验 |
| 归档文书一键生成 | 案卷封面、结案归档登记表、卷内目录、律师工作日志、监督卡、办案小结等自动填充生成 |
| 占位符覆盖值 | 用户可在后台为每个清单项指定自定义替换词内容，无需修改模板即可灵活调整输出 |
| 单份生成与下载 | 每个清单项支持单独生成和下载，方便逐项补充和校验 |
| 监督卡自动检测 | 从结案卷宗中自动检测律师办案服务质量监督卡，支持图片型 PDF 的 OCR 识别回退 |

> **10 秒内，案件文件夹成为一套完整的、有序的、可直接交付的案件卷宗。**

### 🔌 MCP 协议接入

通过 **MCP（Model Context Protocol）**，任何 AI Agent 都可以用自然语言直接调用系统全部能力：

- **200+ API 接口**全面开放
- 查询案件进展、检索客户信息、获取合同数据
- 让法穿 AI 成为律所智能化转型的技术底座

---

## 更多功能

**案件与客户**

| 功能 | 说明 |
|:---|:---|
| 👥 客户管理 | 身份证 OCR 识别、企业信息自动回填 |
| 📋 案件管理 | 全生命周期追踪：阶段流转、当事人管理、律师指派 |
| ⏰ 重要日期提醒 | 开庭/保全到期/举证期限等自动提醒 |
| 🏢 律师团队管理 | 律所/律师/团队信息统一管理 |

**文书与 AI**

| 功能 | 说明 |
|:---|:---|
| 📄 法律文书生成 | docx 模板 + 占位符体系，全类型一键生成 |
| 🤖 AI 诉讼辅助 | WebSocket 对话式文书生成 + 模拟庭审对抗 |
| 🔍 案例检索 | AI 扩展关键词 + LLM 相似度评分 |
| 📑 AI 合同审查 | 错别字检测→条款审查→格式标准化 |

**识别与处理**

| 功能 | 说明 |
|:---|:---|
| 🔎 文书智能识别 | AI 自动分类法院文书、提取案号与关键时间 |
| 📦 PDF 拆解 | 多合一 PDF 自动识别拆分为独立文件 |
| 💬 聊天记录梳理 | 录屏抽帧去重 + OCR 文字提取，导出证据材料 |
| 财产保全日期识别 | AI + 规则引擎双通道提取保全到期时间 |

**工具与集成**

| 功能 | 说明 |
|:---|:---|
| 📡 企业数据查询 | MCP 协议对接天眼查/企查查 |
| 💰 财务工具 | LPR 利率计算器、诉讼费计算器、快递轨迹查询 |
| 🖨️ 批量打印 | 关键词自动匹配打印机和预置参数 |
| 🎬 故事可视化 | 法律文书转时间线/人物关系图动画 |

---

## 快速开始

详见 **[安装与部署指南](INSTALL.md)**。

---

## 分支说明

| 分支 | 说明 |
|:---|:---|
| `main` | 作者维护原始逻辑 |
| `community` | 社区版，接受所有外部 PR，作者不定期将好用的功能合并到 main |

**外部贡献者请将 PR 提交到 `community` 分支。** community 分支的内容作者不会逐行审核，直接合并。觉得好用的功能会合并到 main。

---

## 支持项目

如果这个项目对你有帮助，欢迎支持项目持续发展：

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

---

<p align="center">
  <sub>由一线执业律师主导研发 · 开源 · 私有化部署 · 数据自持</sub>
</p>