<h1 align="center">法穿SI Copilot</h1>

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

法穿SI Copilot 的前身是一个 2022 年用 Django 做的粗糙系统——数据库加几个表单，占位符替换生成 Word，立案功能是另外写的脚本，和系统完全割裂。三年粗放管理下来，一直想重构，但动力不够。

后来参加了司法局的比赛，临时 Vibe Coding 了一个作品，评委送进了决赛。决赛要认真准备，于是就有了法穿SI Copilot——把以前想做的事情，重新做一遍。比赛最后拿了二等奖，金杜也是二等奖。

```
2022-2025 旧系统              →  2026 法穿SI Copilot
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

引入系统后出现了一个荒谬的问题：立案要重复做三次。第一次在法穿SI Copilot 里录入案件信息，第二次在律所 OA 系统里再填一遍，第三次在法院诉讼服务网上再填一遍。明明是几乎相同的内容，居然要填三次。

**核心思路：数据只录入一次，多系统自动流转。** 数据通过 API 推送到 OA 系统，自动填写立案表单。

### 4. 一张网立案

> **⚠️ 重要说明：法穿SI Copilot 不提供一张网自动立案功能。**
>
> 自动填写法院诉讼服务网涉及电子签章、实名认证、CA 证书等强监管环节，不属于本系统的职责范围。如需自动立案，推荐使用专业服务：
>
> - **[律智 365（华宇公司，一张网总舵手）](https://www.lvzhi365.com)** — 成熟的法院诉讼服务网自动立案方案
> - **[吾律AI（幂律智能，法律科技领头羊）](https://wulv.milvzn.com/)** — 一站式智能立案平台
>
> 法穿SI Copilot 的定位是**做好立案前的所有准备工作**——案件信息录入、要素式文书生成、授权委托材料一键生成——确保你带到立案环节的材料已经是可以直接提交的状态。

我们认为立案是律师的核心职责，提交前必须人工审查。

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
| **信息中枢** | IMAP 邮箱 + 收件箱统一聚合，发件人黑白名单过滤 |
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

## 外网访问（Cloudflare Tunnel，可选）

不想买服务器、也没有公网 IP，又想在外网（如手机）访问本机运行的前后端，可以用 Cloudflare Tunnel：本机 `cloudflared` 进程主动向 Cloudflare 边缘建立出站连接，外网流量经固定域名回流，**无需公网 IP、不开路由器端口**；再套一层 Cloudflare Access 做身份门禁，未授权者到不了本机。

以域名 `example.top` 为例，预期效果：`https://app.example.top` → 本机 Vite(5090) → 同源代理 Django(8002)。

1. **前置**：一个域名，DNS 托管到 Cloudflare（免费）；本机安装 `brew install cloudflared`
2. **授权与建隧道**：`cloudflared tunnel login` → `cloudflared tunnel create fachuan`
3. **配置 ingress**（`~/.cloudflared/config.yml`）：

   ```yaml
   tunnel: <隧道UUID>
   credentials-file: /Users/你/.cloudflared/<隧道UUID>.json
   ingress:
     - hostname: app.example.top
       service: http://localhost:5090
     - service: http_status:404
   ```

4. **绑定域名**：`cloudflared tunnel route dns fachuan app.example.top`
5. **前端放行外网 Host**：`frontend/vite.config.ts` 的 `server` 段加 `allowedHosts: ["app.example.top"]`（Vite 默认拒绝非 localhost 的 Host 头）
6. **常驻**：写一个 LaunchAgent（macOS）/ systemd service（Linux）跑 `cloudflared tunnel run fachuan`
7. **门禁（强烈建议）**：Cloudflare 面板 → Zero Trust（免费版 50 席位）→ Access → 创建 Self-hosted 应用绑定 `app.example.top`，策略 Include 你的邮箱（登录方式为邮箱验证码）

**免费额度与限制**：隧道本身无带宽/流量硬限制；Access 免费 50 用户（单人自用绰绰有余）；单请求上传体积上限 100 MB（免费计划）；SAML SSO、设备指纹等高级门禁需付费版。注意：使用 Cloudflare 意味着流量经其边缘中转（TLS 加密），对数据敏感场景请自行评估；也可以随时停用（见下）。

**停用方法**：

```bash
# 停止常驻进程（macOS）
launchctl unload ~/Library/LaunchAgents/com.user.cloudflared-fachuan.plist
# 彻底删除：面板删除 Access 应用与隧道，DNS 删对应 CNAME 即可
```

---

## 专业部署服务

不想自己折腾部署？作者提供**一对一定制部署服务**：

> **先明确一件事：代码始终是免费的。**
> 法穿SI Copilot 全部源码永久免费开源，你可以自行下载、自行部署，**一分钱都不用付**，功能与付费部署完全一致。
> 这笔费用付的**不是软件、不是授权、不是会员订阅**——而是**专业服务**：一位长期实战的法律行业系统开发者投入的时间、经验和一对一的人工支持。

- **作者亲自远程部署**，部署全程附带交流讲解，边部署边答疑，交付即可投入使用
- **每台机器 2000 元** · 一次性专业服务费
- 支持 **Windows / Linux / macOS**（**推荐 macOS**，与开发环境一致，体验最佳）

**这是一笔专业服务费，不是软件授权费**

软件**永久免费**，你为**专业服务**付费。律师给客户开账单时，从来不按「法律条文本身」收费——条文人人可查；收费的是**经验、判断与责任**。部署服务遵循同一个逻辑：

| 免费的部分（软件） | 付费的部分（专业服务） |
|:---|:---|
| 全部源代码，永久开源 | 环境准备、依赖排障、版本匹配 |
| 全部功能，无任何阉割 | 模型、数据库、邮件、法院平台接通 |
| 完整的 `INSTALL.md` 文档 | 历史数据迁移与上线验收 |
| 社区与文档支持 | **一对一人工答疑、有人对结果负责** |

这些环节最常见的结局，是自己折腾两三天仍卡在某一步。付费部署本质是**用专业换时间、用经验换确定性**——把作者已经踩过的坑一次性绕过，让系统当天就能真正跑起来。

如果时间充裕、乐意自己动手，请直接看 **[安装与部署指南](INSTALL.md)** 自行部署，**同样完整可用、同样永久免费**；专业部署服务只是给「不想折腾、希望有人负责到底」的人准备的可选项。

**收入的去向**

部署服务费以**赞助**的形式存在。每一笔收入都投入两个方向：

1. **项目的持续进化** —— 功能迭代、法院平台适配、长期维护，成果继续免费开放给每一位使用者
2. **法律行业的数字化平权** —— 全国超过 **95%** 的中小律所没有自己的 OA。我们在研发一套**免费律所 OA**，把立案、归档、收发文能力带给他们，让最小规模的律所也能与头部律所站在同一条数字化起跑线上

选择部署服务，等于同时做了两件事：**为专业服务付费、换一套当天就能跑起来的系统，并赞助一个行业级的开源理想。**

需要部署服务，可通过下方公众号「法穿」联系作者。

---

## 支持项目

如果这个项目对你有帮助，欢迎成为**项目共建人**（含上方部署服务在内，所有收入均投入法穿SI Copilot 与免费律所 OA 的后续开发）：

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
