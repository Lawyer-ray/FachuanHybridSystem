# 银行批量诉讼（场景 2）交付说明

> 分支：`feat/prototype-bank-litigation-full`
> 日期：2026-10-30
> 适用账号：运营管理员账号（下称「演示账号」）

---

## 一、做了什么

把原型里画的那条链路，**在真实前端里做出来并接上真后端**：

```
一份委托 → 批量出案 → 起诉条件校验 → 要素式转换
        → OA 立案 → 一张网立案 → OA 盖章 → OA 归档
```

### 新增前端 feature

`frontend/src/features/bank-litigation/`

| 文件 | 职责 |
|---|---|
| `api/index.ts` | 契约层：cases / doc-convert / oa-filing / court-filing 四个域 |
| `hooks/use-cases.ts` | 读取态：案件、材料齐备度、起诉条件、立案前置信息、OA 凭证 |
| `hooks/use-auto-run.ts` | 通用「提交 → 轮询会话」状态机（OA 与一张网共用） |
| `components/CaseListPage.tsx` | 案件列表，待立案优先排序 |
| `components/ReadinessPanel.tsx` | 起诉条件 + 材料齐备并排展示 |
| `components/DocConvertPanel.tsx` | 传统文书 → 要素式文书 |
| `components/FilingPanels.tsx` | 律所 OA 与一张网两个外部系统入口 |
| `components/OAActionPanels.tsx` | OA 盖章 / OA 归档（共用面板，先反查再提交） |
| `components/BankLitigationPage.tsx` | 页面装配（列表 / 工作台） |

### 路由

- `/bank-litigation` —— 案件列表
- `/bank-litigation/:id` —— 指定案件的立案工作台

六个分区（按律师实际推进顺序排，不按功能模块）：

`起诉条件 → 要素式转换 → OA 立案 → 一张网立案 → OA 盖章 → OA 归档`

---

## 二、后端修了 3 个真实缺陷

这些都是**做前端时撞出来的**，不是主动重构。

### 1. `readiness` 中英文混存 → 静默假通过

生产库 `cases_case.current_stage` 是混存的：

```
first_trial 48 / enforcement 18 / 一审 13 / second_trial 7 / 二审 1
```

原实现只认英文枚举。后果：**13 件「一审」落进 `mode=other`，`checks` 为空、
`ready` 恒为 `True`** —— 律师看到「全部通过」，实际一条都没校验过。
静默假通过比报错更危险。

同一问题出现在 `legal_status`（`defendant 73 / plaintiff 45 / 被告 3`），
3 个中文「被告」不算被告，误判「主体不适格」。

**修复**：阶段与当事人地位白名单同时收英文枚举与中文显示名。

### 2. OA 立案会话被同名 schema 顶掉

`oa_filing.SessionOut` 与 `social_auth.SessionOut` 同名。OpenAPI 的
`components.schemas` 以类名为 key，只有一个能活 —— 实测被 social_auth 顶掉。

后果：契约里 oa-filing 返回 `{success, goto, state, expires_in, message}`，
**没有 `id`**。前端照契约写永远拿不到 `session_id`，轮询起不来；
而生成物「有类型」，编译器不报错。

**修复**：改名 `FilingSessionOut`（同目录 `ArchiveSessionOut` /
`StampSessionOut` 本来就带领域前缀，只有这个漏了）。

### 3. 坏文件报成 502「服务不可用」

上传内容损坏的 `.docx`（扩展名对、ZIP 结构坏），接口返回 **502**。
502 语义是「上游服务挂了」——网关当故障、律师去报障，
真实原因只是这一个文件打不开。

**修复**：补 `_assert_parsable` 前置校验（docx 走 zipfile 目录、.doc 认 OLE2
魔数、pdf 认 `%PDF` 头、空文件直接拒），返回 `400 FILE_CORRUPTED` + 人话。

---

## 三、Mock 数据

### 建库脚本

`frontend/prototype/2026.10.25-银行批量诉讼原型/scripts/seed-mock-db.py`

- 所有对象名带 `[原型演示]` 前缀，**绝不碰真实案件**
- `--purge` 只按前缀删，可重复执行
- 挂在演示账号下

建的东西：

| 类型 | 内容 |
|---|---|
| 合同 | 1 份（含委托方 + 主办律师，缺这两项 OA 立案必失败） |
| 案件 | 3 件（一审待起诉 / 一审已结 / 二审） |
| 材料 | 11 份，**每份都挂真实 PDF**（一张网要校验文件内容） |
| 文件夹绑定 | 3 个本地卷宗目录（盖章/归档的唯一入口） |
| OA 案号 | `2026YSDEMO001`（反查命中后必须有它，否则 404） |

一张网 civil 立案要 5 个槽位：起诉状 / 人员身份证明 / 授权委托 / 证据目录 / 送达地址确认书。
缺哪个接口就回「缺少 XX 材料（slot N）」—— 我第一版就漏了起诉状。

### 生成真实文书文件

`frontend/prototype/2026.10.25-银行批量诉讼原型/scripts/gen-mock-docs.py`

从 `js/mock-case-real.js` 取事实，生成 18 个真实 docx / pdf 到 `mock-out/`。
**保留原件 5 处矛盾**（合同号、身份证号、贷款金额、购房地址、利息说明截断）——
那是演示「AI 发现矛盾」的素材，抹平反而失真。

---

## 四、验证结果

### 端到端（20 项全过）

```bash
E2E_USER=<账号> E2E_PASS=<密码> node frontend/e2e/bank-litigation.e2e.mjs
```

```
✓ 登录成功
✓ 后端有演示案件  3 件
✓ 案件列表渲染出演示案件
✓ 起诉条件逐条与后端一致  5 条
✓ 条件面板标题与本阶段匹配  filing
✓ 材料槽位逐项与后端一致  6 槽位
✓ 要素式转换成功并下载  要素式-e2e-传统起诉状.docx
✓ OA 凭证状态与后端一致
✓ 管辖法院与后端一致  佛山市南海区人民法院
✓ OA 立案：提交后进入轮询
✓ 一张网立案：提交后拿到会话状态
✓ 一张网立案：到达终态
✓ OA 盖章：文件路径能反查到合同  contract=406 oa_no=2026YSDEMO001
✓ OA 归档：文件路径能反查到合同
✓ OA 盖章面板已渲染
✓ OA 归档面板已渲染
✓ 无前端 JS 错误
```

### 真实外部系统调用记录

**OA 立案**（session 93）：
```
02:09:52  SSO 登录: 打开 OA 登录页
02:10:04  SSO 登录: 请用企业微信扫码（等待 180 秒）
02:14:13  案件信息填写完成
02:14:22  合同信息填写完成
02:14:25  存草稿完成，当前URL: .../PROJECT003
02:14:25  Playwright 立案流程完成
→ status=completed
```

**一张网立案**（session 319）：
```
t+015s  in_progress   HTTP阶段: HTTP主链路：正在提交一张网草稿
t+030s  completed     民事一审HTTP立案完成（未提交）
```

注意「**未提交**」—— 这是设计如此：机器填到头，最后一下必须律师点。

### 常规测试

| 项 | 结果 |
|---|---|
| 前端 `tsc --noEmit` | 0 错 |
| 前端 `eslint src` | 0 错 |
| 前端 `vitest` | 2628 passed |
| 后端 doc_convert / oa_filing / cases / court_filing | 全过 |
| `vite build` | 通过 |

---

## 五、你手工测试时怎么做

### 1. 起服务

```bash
# 后端（如果没在跑）
cd backend && make
# 前端
cd frontend && pnpm dev
```

### 2. 建演示数据

```bash
cd /Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem
backend/.venv/bin/python "frontend/prototype/2026.10.25-银行批量诉讼原型/scripts/seed-mock-db.py"
```

脚本末尾会打印 `no=1 → backendId: 421` 这样的映射，同步到
`js/store.js` 才能让原型也指对案件（E2E 会自动同步）。

### 3. 打开页面

浏览器登录后访问 **`http://localhost:5090/bank-litigation`**

### 4. 走一遍

1. 列表里有 3 件 `[原型演示]` 案件，第一件（待起诉）排最前
2. 点进去 → **起诉条件**：5 项逐条列出，缺件标红
3. **要素式转换**：选一份 `mock-out/` 里的起诉状 docx → 转换并下载
4. **OA 立案**：点「在 OA 立案」→ 会弹出 OA 登录页**等你扫码**
5. **一张网立案**：点「推送到一张网」→ 约 30 秒后显示 `completed`
6. **OA 盖章**：填 `~/Downloads/原型演示卷宗/1-一审/催收记录.pdf`
   → 点「反查合同」→ 显示合同与 OA 案号 → 才可提交
7. **OA 归档**：同上，可一次填多个路径（每行一个）

盖章/归档必须先「反查合同」再提交：这两个动作的入参是**文件路径**，
后端按文件所在目录反查文件夹绑定。路径不在绑定目录里就 404。

---

## 六、已知边界

| 项 | 说明 |
|---|---|
| OA 立案要扫码 | 走企业微信 SSO，需人工扫。自动化只能到「弹码」这一步 |
| 一张网「未提交」 | 刻意设计：机器填表，提交按钮留给律师 |
| 列表无分页 | 当前拉全量。真实案件上千时需加分页（后端已支持 `page_size`） |
| 盖章/归档提交未跑通真实 OA | 反查链路已验证；真提交需要 OA 里存在对应案号，演示案号必然搜不到 |
| 执行立案需先有裁判文书 | 无登记案号时按钮禁用（前端前置拦截，不等后端失败） |
| 原型仍在用 mock | `frontend/prototype/` 是画稿，真实页面在 `frontend/src/` |

---

## 七、改动清单

```
backend/apps/cases/services/case_readiness_service.py     中英文混存兼容
backend/apps/cases/models/case.py                          group_key / group_name
backend/apps/cases/migrations/0043_case_group.py
backend/apps/cases/api/case_readiness_api.py               3 个新端点
backend/apps/cases/services/case_readiness_service.py      材料槽位两轮匹配
backend/apps/doc_convert/exceptions.py                     FileCorruptedError
backend/apps/doc_convert/services/doc_convert_service.py   _assert_parsable
backend/apps/oa_filing/schemas/filing_schemas.py           FilingSessionOut
backend/plugins/court_automation/filing/schemas.py         中文当事人地位
backend/apiSystem/apiSystem/settings.py                    CORS 白名单加 :8080

frontend/src/features/bank-litigation/                    整个 feature（新）
frontend/src/app/paths.ts                                  /bank-litigation 路由
frontend/src/app/router.tsx
frontend/src/app/preload.ts
frontend/src/types/api-schema.d.ts                         OpenAPI 重新生成
frontend/e2e/bank-litigation.e2e.mjs                       E2E 脚本（新）
```

### 提交记录

```
9d270ebe feat(bank-litigation): 补齐 OA 盖章、OA 归档、执行立案切换
9e1cbb77 test(e2e): 银行批量诉讼全链路端到端脚本
80b21c25 chore(plugins): 更新 court_automation 子模块指针
4fce7502 fix(doc-convert): 坏文件不再报成 502；一张网兼容中文当事人地位
2212fb79 feat(bank-litigation): 银行批量诉讼场景 2 前端入口 + OA schema 修复
6a7be730 fix(cases): 就绪度兼容中英文混存阶段与当事人地位
```
