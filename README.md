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

## 为什么做这个系统

法穿 AI Copilot 的前身是一个 2022 年用 Django 做的粗糙系统——数据库加几个表单，占位符替换生成 Word，立案功能是另外写的脚本，和系统完全割裂。三年粗放管理下来，一直想重构，但动力不够。

后来参加了一个比赛，临时 Vibe Coding 了一个作品，评委送进了决赛。决赛要认真准备，于是就有了法穿 AI Copilot——把以前想做的事情，重新做一遍。

```
2022-2025 旧系统              →  2026 法穿 AI Copilot
Django + DRF 脚本拼凑          →  Django 6 + React 19 + MCP
只能填模板生成 Word             →  一次生成无需修改的完整合同
立案脚本和系统割裂              →  OA 立案 + 一张网立案统一入口
粗放管理 Excel 辅助             →  127 个模型 · 483 个 API · 35 个模块
```

---

## 五个核心功能

整个系统围绕一个核心设计：**文件夹**。每个案件绑定一个文件夹——短信文书下载到文件夹、合同文件生成到文件夹、归档材料从文件夹自动收集。绑定一次，处处受益。

### 1. 法院短信自动处理

律师每天收到大量法院短信——文书送达、立案通知、交费通知。以前每条短信要手动处理：打开链接、下载文书、找到对应案件、归档、通知团队。一条短信5分钟。

现在**律师只需转发短信，之后一切自动完成**：

```
转发法院短信
  → 智能解析案号 / 当事人 / 案件类型（支持 6 种法院送达平台）
  → 自动下载文书 PDF
  → 推荐匹配案件（算法评分 + 人工确认）
  → 规范重命名 → 自动归档到案件文件夹
  → 飞书 / Telegram / 企业微信实时通知团队
```

7×24 小时无人值守运行。匹配做不到 100%，所以用**推荐算法**把最可能的案件按评分列出来，律师点一下就行——比追求全自动更务实。

### 2. 一次生成、无需修改的合同

旧系统只能用占位符填模板，生成出来的合同要人工再改。因为合同里的规则太复杂了——一个委托代理合同下面有三个借贷纠纷案件，张三律师代理其中两个、李四律师代理一个，每个案件的收费模式不同（固定收费 / 半风险 / 全风险）。占位符根本处理不了这种逻辑。

新系统把合同数据结构化了——合同、当事人、收费模式、代理阶段、案件关联，全部是独立模型。生成逻辑不再是简单的占位符替换，而是根据数据模型的关联关系，用 Java 微服务按规则生成 Word 文档。

**目标：一次生成，打印盖章即可，无需修改。** 合同做到了，全套授权委托材料（所函、授权委托书、法定代表人身份证明书）也一并解决了。

### 3. 打通 OA 立案

引入系统后出现了一个荒谬的问题：立案要重复做三次。第一次在法穿 AI Copilot 里录入案件信息，第二次在律所 OA 系统里再填一遍，第三次在法院诉讼服务网上再填一遍。明明是几乎相同的内容，居然要填三次。

**核心思路：数据只录入一次，多系统自动流转。** 数据通过 API 推送到 OA 系统，自动填写立案表单。

### 4. 一张网立案

两种技术方案并存：Playwright 浏览器自动化（开源版本）和 API 直连方案（内部使用）。API 方案几秒钟就能填完一个案件信息。

一个重要的产品决策：**只做到保存，不帮用户点提交。** 立案是律师的核心职责，提交前必须人工审查。AI 帮你把 99% 的活干了，最后 1% 的审查权留给律师。

> 自动化应该止步于责任边界。这不是技术做不到，是产品选择。

### 5. 一键归档

案件结了，事情没完。以前的流程：从 OA 下载 Excel → 邮件合并生成文件夹模板 → 手动找材料 → 逐个转 PDF → 合并卷宗 → 统计页码 → 打印。一个案件大概 10 分钟。

现在：

```
绑定文件夹 → 自动同步材料 → 归档清单一目了然
→ 一键生成：封面 + 登记表 + 卷内目录 + 合并 PDF + 页码统计
```

归档清单根据案件类型自动生成（诉讼 20 项、刑事 18 项、非诉 12 项），扫描文件夹自动分类，还有一个**会学习的分类器**——手动调整过一次分类，下次同类文件就自动归对了。

---

## 更多能力

| 类别 | 能力 |
|:---|:---|
| **AI 工作台** | 多会话对话、流式输出、工具调用审批、多模型切换（Ollama / 云端 API） |
| **MCP 协议** | 200+ API 全面开放，任何 AI Agent 可用自然语言调用系统全部能力 |
| **信息中枢** | IMAP 邮箱 + 一张网收件箱统一聚合，发件人黑白名单过滤 |
| **企业查询** | MCP 协议对接天眼查/企查查，自动回填企业信息 |
| **案件管理** | 18 种阶段流转、案件链追溯、收款跟踪、重要日期提醒 |
| **文书生成** | docx 模板 + 占位符体系，起诉状/代理词/法律意见书全类型一键生成 |
| **PDF 拆解** | 多合一 PDF 自动识别拆分，OCR 逐页分类 |
| **聊天记录取证** | 录屏自动抽帧、智能去重、OCR 文字提取，导出证据材料 |
| **财务工具** | LPR 利率分段计算、诉讼费核对、快递轨迹查询 |
| **要素式文书** | 支持 40+ 种文书类型一键转换为一张网要求的要素式格式 |

---

## 技术栈

| 层级 | 技术 |
|:---|:---|
| **前端** | React 19 + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| **后端** | Django 6 + Django Ninja + Django Q2 + Channels |
| **数据库** | PostgreSQL + Valkey |
| **AI/LLM** | OpenAI API 兼容 · Ollama 本地模型 · WebSocket 流式对话 |
| **部署** | Docker · 私有化部署 · 数据自持 |

---

## 快速开始

详见 **[安装与部署指南](INSTALL.md)**。

---

## 分支说明

| 分支 | 说明 |
|:---|:---|
| `main` | 作者维护原始逻辑 |
| `community` | 社区版，接受所有外部 PR，作者不定期将好用的功能合并到 main |

**外部贡献者请将 PR 提交到 `community` 分支。**

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
