# TECH-DEBT.md —— AI 平台与检索的未完成项（唯一 backlog 入口）

> 本文件只记**已经确认、但这一轮没做**的技术债，每条都带「现象 / 证据 / 修法 / 代价」。
> 做完一条就把那一条删掉，并在 `changelog/` 写一条对应版本记录。
>
> 为什么放根目录：`docs/` 被 `.gitignore:257` 整个忽略（`git ls-files docs` 为空），
> 写在那里等于没写——其他 AI 会话与后来的人都看不到。本文件**在 git 里**。
>
> 最近一次更新：2026-11-21（当前**无未完成项**；⑤ 经压测关闭、⑥ 已随 `v27.21.1` 结清）。
>
> **已完成**（不在本清单里了）：
> - ① 成本归属缺 provider 维度 → `v27.20.11`（`LLMCallRecord` / `AgentRun` 加 provider + 写入 + `by_provider`）
> - ③ `fallback_models` 只解一半 → `v27.20.11`（非流式路径按降级链重试）
> - ⑥ agent 后端埋点缺口（dsh 无 `tool/result` 与 usage、openai-agents 无 usage 且单栏双 `done`、
>   平台解析在 async 上下文读同步 ORM）→ `v27.21.1`（三条全部补齐，真机四栏验收通过）

---

## ⑤ 主对话路径的精确在飞计数 —— **实测不需要，已关闭**

**原顾虑**：pi / dsh / openai-agents 在外部进程里直接跟网关说话，拿不到请求边界，
选 Key 只能轮转；担心高并发单栏提问会把同一把 Key 压过 `max_parallel_requests=3` → 429。

**实测（2026-11-21，真实网关，10 把 Key × 每把 3 并发 = 30 槽位）**

| 并发（同时在飞的请求） | 短请求（16 token，~0.4s） | 真实轮次（~250 字，~2s） |
|---|---|---|
| 10 | 10/10 成功 | 10/10 成功（总耗时 2.0s） |
| 20 | 20/20 成功 | 20/20 成功（1.9s） |
| 30 = 全部槽位 | 30/30 成功 | 30/30 成功（2.4s） |
| 40（超容量 133%） | **3 个 429**（`retry-after: 60`） | — |

**并且**：在 40 并发时，租约模式（模拟 ⑤ 的实现）拿到 **5 个 429**，比现状的 3 个更差——
因为 `KeyScheduler.allocate` 在饱和时是「循环复用、best-effort 不报错」，
它并不能凭空造出第 31 个槽位。

**结论**：如果出现 429，瓶颈是**总槽位 30**（= key 数 × 每 Key 并发），不是"选得不准"。
⑤ 解决不了容量问题，只增加租约泄漏、外部进程崩溃、TTL 兜底等真实风险。
**不做**。真要提高容量，正确的动作是加 Key（30 → 每加一把 +3 槽位）。

**重开条件**：若将来出现「并发 < 容量上限却仍频繁 429」，说明挑选确实偏斜，
届时再做（方案见 git 历史：租约 + 5 分钟 TTL + 失败回报冷却）。

## 怎么验证这些"还没做"

```bash
# ① 成本归属：应当无输出（说明确实没有 provider 字段）
rg -n "provider\s*=\s*models" backend/apps/agent/models/run.py

# ② rpm/tpm：应当无输出
rg -n "rpm|tpm" backend/apps/core/models/llm_provider.py

# ③ fallback_models 的运行时消费者：应当只有 pi/服务层，没有 openai_compatible
rg -ln "fallback_models" backend/apps --glob '!**/__pycache__/**'

# ④ 抽取依赖：应当「未引入」
rg -n "trafilatura|htmldate" backend/pyproject.toml

# ⑤ 选 Key 是否占槽：key_selector 里应当看不到 acquire
rg -n "acquire" backend/apps/core/llm/key_selector.py
```
