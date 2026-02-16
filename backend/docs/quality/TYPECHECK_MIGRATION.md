## 目标

- 保持全局 strict-ish 配置不回退（`disallow_untyped_defs` 等）
- 将 `ignore_errors=True` 从“大块忽略”逐步拆成“可移除的小块”
- 让类型质量收敛有可见度：每次迭代能明确减少一个 ignore 区块或缩小 ignore 范围

## 当前大块 ignore（核心）

- `apps.core.config.*`：保留 ignore，按子包拆分移除
- `apps.core.dependencies.*`：保留 ignore，优先补齐返回类型与 Protocol 约束
- `apps.core.llm.*`：保留 ignore，优先修复边界类型与 Any 扩散
- `apps.core.infrastructure.*`：保留 ignore，优先修复公共基础设施类型

对应配置位置见 `backend/mypy.ini` 的 “Core sub-modules” 区块。

## 收敛策略（可直接落地）

### 1) 先让“新代码”永远不进 ignore

- 新增模块/文件默认不加 ignore；如果必须加，必须给出移除条件（例如：拆出 Protocol 后再移除）。

### 2) 把 ignore 从包级拆成文件级

做法：

- 将 `apps.core.config.*` 拆成 `apps.core.config.providers.* / schema.* / migration.* / ...` 的独立段落。\n- 每次只挑一个子包把 ignore 去掉或缩小（例如只保留 `providers.yaml` 的 ignore，其余放开）。\n- 对“已经干净”的子包设置 `ignore_errors = False`，并在下一轮移除整个段落。

### 3) 每次迭代的度量标准

满足任意一条即可视为“类型质量前进了一步”：

- 删除 1 个 `ignore_errors=True` 段落\n- 将 1 个包级 ignore 拆成 2 个更小段落（范围更小）\n- 为 1 个 dependencies build_* 函数补齐返回类型（配合 Protocol），并移除对应文件的 ignore

### 4) 推荐的优先顺序（Core）

1. `apps.core.dependencies.*`：先补返回类型与 Protocol（成本低、收益高）\n2. `apps.core.infrastructure.*`：公共模块类型修复能带动全局\n3. `apps.core.config.*`：拆分子包逐步放开\n4. `apps.core.llm.*`：最后集中处理 Any 与第三方 SDK typing

## 审查清单（每次 PR）

- 是否新增了 ignore 段落？如有，是否有明确移除路径\n- 是否把 Any 从组合根（dependencies/service locator）向业务层扩散\n- 是否为跨模块能力新增/调整了 Protocol，并把返回类型落实到 build_* / ServiceLocator getter
