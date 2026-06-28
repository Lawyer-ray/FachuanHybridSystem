export const meta = {
  name: 'async-audit-round2-cross-review',
  description: '第二轮交叉复查：7 个 agent 验证第一轮 findings 并扫描遗漏',
  phases: [
    { title: 'Cross-Review', detail: '6 个 agent 复查第一轮发现', model: 'opus' },
    { title: 'Global-Scan', detail: '1 个 agent 全局扫描遗漏模式', model: 'opus' },
    { title: 'Synthesis', detail: '汇总复查结果', model: 'opus' },
  ],
}

const REVIEW_PROMPT = (label, findingsPath, scope) => `你是异步化审计复查专家。你的任务是验证第一轮审计的 findings 是否准确，并发现遗漏。

## 你的审查范围
${scope}

## 工作流程

### Step 1: 读取第一轮 findings
读取文件 \`${findingsPath}\`，获取所有 findings 列表。

### Step 2: 逐条验证每条 finding
对每条 finding：
1. 读取 finding 指向的源文件（使用 Read 工具）
2. 跳转到指定行号，检查上下文
3. 判断：
   - **confirmed**: 确实存在该问题
   - **false_positive**: 误报（比如已经是 async、或 ORM 调用在同步上下文中是正确的、或 Django Ninja 已自动线程池包装）
   - **downgrade**: 确实有问题但 severity 应降低（如 P0→P1 或 P1→P2）
   - **upgrade**: severity 应提高
4. 检查级联影响：改为 async 后是否需要同时修改调用方？

### Step 3: 扫描遗漏
在你负责的目录中，搜索第一轮可能遗漏的模式：
- \`async def\` 函数内使用 \`list(\` 或 \`for ... in \` 遍历 ORM queryset
- \`async def\` 函数内调用同步方法但没有 \`sync_to_async\` 包装
- Django Ninja 的 \`@router.get/post/put/delete\` 如果是 \`def\` 而非 \`async def\`，内部有 ORM 操作
- \`sync_to_async\` 用在了不必要的地方（比如函数本身就在同步上下文）
- \`httpx.Client\` 用在 async 上下文（应用 \`httpx.AsyncClient\`）
- 文件 I/O（\`open()\`, \`Path.read_bytes()\` 等）在 async 视图/函数中

### 注意事项
- models.py 中的模型定义不需要审查
- Django Admin 注册不需要审查
- test_ 文件跳过
- __init__.py 跳过
- 如果一个同步函数只在同步 worker（Celery/Django-Q）中被调用，那么它的同步 ORM 是正确的，应标为 false_positive
- Django Ninja 同步视图（\`def\` 而非 \`async def\`）会被自动包装到线程池，虽然不是最优但不会阻塞事件循环，severity 应为 P2
- 如果已有 async 版本（函数名以 a 开头或带 _async 后缀），应优先建议使用已有版本

## 输出格式

请直接输出 JSON（不要包裹在 markdown 代码块中）：

{
  "agent": "${label}",
  "reviewed_findings": [
    {
      "original_file": "xxx",
      "original_line": 42,
      "verdict": "confirmed | false_positive | downgrade | upgrade",
      "new_severity": "P0 | P1 | P2",
      "reason": "判断理由（简要说明为什么确认/误报/升降级）",
      "cascade_impact": ["需要级联修改的文件列表，若无需改动则为空数组"],
      "revised_suggestion": "修正后的建议（仅在与原建议不同时填写，否则留空字符串）"
    }
  ],
  "new_findings": [
    {
      "file": "xxx",
      "line": 42,
      "function": "func_name",
      "category": "sync_orm | sync_http | sync_io | sync_sleep | sync_task | sync_signal | sync_middleware | sync_callchain",
      "severity": "P0 | P1 | P2",
      "current": "问题描述",
      "suggestion": "修复建议",
      "impact": "影响说明"
    }
  ]
}`

const GLOBAL_SCAN_PROMPT = `你是异步化审计全局扫描专家。你的任务是在整个后端代码库中搜索第一轮审计可能遗漏的异步化问题。

## 扫描目标目录
- backend/apps/
- backend/plugins/

## 扫描模式

### 模式 1: async def 内的同步 ORM 遍历
搜索：在 async def 函数中使用 \`list(\` 包裹 queryset、或 \`for obj in Model.objects.xxx\` 同步遍历。
Grep 模式：先找到 async def 函数，然后检查函数体内是否有同步 ORM 调用。
工具：先用 Grep 搜索 \`async def\`，然后检查每个函数体内是否有 .objects. 调用。

### 模式 2: sync_to_async 使用审查
搜索所有 \`sync_to_async\` 使用，检查：
- 是否在已经有 async 版本的函数上使用了 sync_to_async（应该直接用 async 版本）
- sync_to_async 的 thread_sensitive 参数是否正确
- 是否有遗漏：同步函数被 async 上下文调用但没用 sync_to_async

### 模式 3: HTTP 客户端最佳实践
搜索 \`httpx.Client\` 和 \`httpx.get/post\` 使用，检查：
- 是否在 async 上下文中用了同步 httpx（应该用 httpx.AsyncClient）
- AsyncClient 是否正确关闭（async with 或 await client.aclose()）

### 模式 4: async def 中的 await 缺失
搜索 async def 函数内调用其他 async 函数但没有 await 的情况（较罕见但危险）

### 模式 5: Django Ninja 视图函数
搜索所有 Django Ninja router 的 @router.get/post/put/delete 装饰器，检查：
- 视图函数是 def 还是 async def
- 如果是 def 且内部有 ORM 操作 → 标记（但 severity 为 P2，因为 Django Ninja 自动线程池包装）
- 如果是 async def 且内部有同步 ORM → 标记为 P0

## 工作方式
1. 对每个模式，使用 Grep 搜索相关代码
2. 对找到的可疑代码，用 Read 读取上下文确认
3. 跳过 tests/、__init__.py、models.py（纯模型定义）

## 输出格式

请直接输出 JSON：

{
  "agent": "global-scan",
  "reviewed_findings": [],
  "new_findings": [
    {
      "file": "xxx",
      "line": 42,
      "function": "func_name",
      "category": "sync_orm | sync_http | sync_io | sync_sleep | sync_task | sync_signal | sync_middleware | sync_callchain",
      "severity": "P0 | P1 | P2",
      "current": "问题描述",
      "suggestion": "修复建议",
      "impact": "影响说明"
    }
  ]
}`

const GROUPS = [
  { label: 'A', findingsPath: 'audit/review-group-a-findings.json', scope: 'automation + documents' },
  { label: 'B', findingsPath: 'audit/review-group-b-findings.json', scope: 'cases + core' },
  { label: 'C', findingsPath: 'audit/review-group-c-findings.json', scope: 'contracts/client + litigation_ai/legal_research/legal_solution' },
  { label: 'D', findingsPath: 'audit/review-group-d-findings.json', scope: 'organization/social_auth/enterprise_data/message_hub + oa_filing/finance/evidence/evidence_sorting/reminders' },
  { label: 'E', findingsPath: 'audit/review-group-e-findings.json', scope: 'batch_printing/chat_records/contacts/doc_convert/doc_converter/docspace + document_parsing/document_recognition/express_query/image_rotation/invoice_recognition' },
  { label: 'F', findingsPath: 'audit/review-group-f-findings.json', scope: 'pdf_splitting/story_viz/workbench/workflow/testing + plugins' },
]

log('🔍 启动第二轮交叉复查：6 个复查 agent + 1 个全局扫描...')

// Run all 7 agents in parallel
const results = await parallel([
  ...GROUPS.map(g => () =>
    agent(
      REVIEW_PROMPT(g.label, g.findingsPath, g.scope),
      { label: `review:${g.label}(${g.scope})`, phase: 'Cross-Review', model: 'opus' }
    )
  ),
  () =>
    agent(
      GLOBAL_SCAN_PROMPT,
      { label: 'review:G(全局扫描)', phase: 'Global-Scan', model: 'opus' }
    ),
])

log('✅ 所有复查 agent 完成，开始汇总...')

// Parse results
const allReviewed = []
const allNewFindings = []
const agentLabels = [...GROUPS.map(g => g.label), 'G']

for (let i = 0; i < results.length; i++) {
  const raw = results[i]
  if (!raw) {
    log(`⚠️ Agent ${agentLabels[i]} 返回空结果`)
    continue
  }
  try {
    let jsonStr = raw
    const match = raw.match(/\{[\s\S]*"reviewed_findings"[\s\S]*\}/)
    if (match) jsonStr = match[0]
    const parsed = JSON.parse(jsonStr)
    if (parsed.reviewed_findings) allReviewed.push(...parsed.reviewed_findings.map(f => ({ ...f, _reviewer: agentLabels[i] })))
    if (parsed.new_findings) allNewFindings.push(...parsed.new_findings.map(f => ({ ...f, _reviewer: agentLabels[i] })))
  } catch (e) {
    log(`⚠️ Agent ${agentLabels[i]} JSON 解析失败: ${e.message}`)
  }
}

// Calculate verdict stats
const verdicts = { confirmed: 0, false_positive: 0, downgrade: 0, upgrade: 0 }
for (const r of allReviewed) {
  if (r.verdict in verdicts) verdicts[r.verdict]++
}

// Recalculate severity distribution
const finalSev = { P0: 0, P1: 0, P2: 0 }
for (const r of allReviewed) {
  if (r.verdict !== 'false_positive' && r.new_severity in finalSev) {
    finalSev[r.new_severity]++
  }
}
for (const f of allNewFindings) {
  if (f.severity in finalSev) finalSev[f.severity]++
}

log(`📊 复查完成：reviewed=${allReviewed.length}, confirmed=${verdicts.confirmed}, false_positive=${verdicts.false_positive}, downgrade=${verdicts.downgrade}, upgrade=${verdicts.upgrade}, new=${allNewFindings.length}`)
log(`📊 最终严重度分布：P0=${finalSev.P0}, P1=${finalSev.P1}, P2=${finalSev.P2}`)

return {
  verdicts,
  finalSev,
  reviewed: allReviewed,
  newFindings: allNewFindings,
  summary: {
    totalReviewed: allReviewed.length,
    confirmed: verdicts.confirmed,
    false_positive: verdicts.false_positive,
    downgrade: verdicts.downgrade,
    upgrade: verdicts.upgrade,
    newFindingsCount: allNewFindings.length,
    finalP0: finalSev.P0,
    finalP1: finalSev.P1,
    finalP2: finalSev.P2,
  },
}
