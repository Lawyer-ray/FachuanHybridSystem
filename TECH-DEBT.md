# TECH-DEBT.md —— AI 平台与检索的未完成项（唯一 backlog 入口）

> 本文件只记**已经确认、但这一轮没做**的技术债，每条都带「现象 / 证据 / 修法 / 代价」。
> 做完一条就把那一条删掉，并在 `changelog/` 写一条对应版本记录。
>
> 为什么放根目录：`docs/` 被 `.gitignore:257` 整个忽略（`git ls-files docs` 为空），
> 写在那里等于没写——其他 AI 会话与后来的人都看不到。本文件**在 git 里**。
>
> 最近一次更新：2026-11-21。
>
> **已完成**（不在本清单里了）：
> - ① 成本归属缺 provider 维度 → `v27.20.11`（`LLMCallRecord` / `AgentRun` 加 provider + 写入 + `by_provider`）
> - ③ `fallback_models` 只解一半 → `v27.20.11`（非流式路径按降级链重试）

---

## ⑤ 主对话路径只有「读侧」健康过滤，没有精确在飞计数

**现象**：pi / dsh / openai-agents 在**外部进程**里直接跟网关说话，我们只能给它们一把 Key，
拿不到"请求开始/结束"，所以**无法**像 core 路径那样给它们占槽位。目前做到的是：
- 选 Key 时跳过别的进程判定冷却中的（`key_selector`，v27.20.7）；
- 多答/压缩这两条**有租约**的路径是精确计数（`key_scheduler`）。

仍未解决：律师单栏提问同时来 10 个，可能选中同一把 Key 并撞 `max_parallel_requests=3`。

**证据**：`apps/core/llm/key_selector.py` 只做过滤 + 轮转，不占槽；
`apps/agent/backends/key_scheduler.py` 的注释明确写了"进程内记账、跨 worker 需 Redis 而收益不抵"。

**修法（若要做）**：把 `KeyScheduler` 的在飞计数做成**租约式**——每轮开始 `allocate(1)`、
轮结束 `release`，并由 `stream.py` 统一持有；失败时回报 `success=False` 让该 Key 进冷却。
代价 M；风险：外部进程崩溃时租约泄漏（要有 TTL 兜底），所以要做成"租约 5 分钟自动过期"。

---

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
