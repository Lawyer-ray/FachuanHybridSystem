export const meta = {
  name: 'async-fix-step3-litigation',
  description: 'Step 3: async 化 litigation_ai agent tools + context service + draft service',
  phases: [
    { title: 'Fix', detail: 'litigation_ai P1 修复', model: 'opus' },
  ],
}

log('🔧 Step 3: async 化 litigation_ai')

const result = await agent(
  `你是 Django async 修复专家。修复 litigation_ai 模块的 async 问题。

## 背景
- \`session_repository.py\` 已有完整双 API（sync/async），无需修改
- \`context_service.py\` 已有 \`abuild_case_info\` 但 draft_service 没用它
- \`tools.py\` 中 4 个 tool 没有 async_func，全靠 sync_to_async fallback
- \`litigation_consumer.py:185\` 已正确使用 database_sync_to_async，无需修改

## 修复步骤

### Step 1: Read 所有相关文件
- \`backend/apps/litigation_ai/agent/tools.py\`
- \`backend/apps/litigation_ai/services/session/context_service.py\`
- \`backend/apps/litigation_ai/services/generation/draft_service.py\`
- \`backend/apps/litigation_ai/services/evidence/evidence_rag_service.py\`
- \`backend/apps/litigation_ai/services/evidence/evidence_digest_service.py\`
- \`backend/apps/litigation_ai/services/session/session_lifecycle_service.py\`

### Step 2: context_service.py — 添加 async 方法

在 \`get_case_info_for_agent\` 附近添加:
\`\`\`python
async def aget_case_info_for_agent(self, case_id: str) -> dict[str, Any]:
    """异步版本：获取案件详情供 Agent 使用。"""
    from asgiref.sync import sync_to_async
    case_dto = await sync_to_async(
        get_case_service().get_case_with_details_internal
    )(case_id)
    return self._format_case_info(case_dto)
\`\`\`

在 \`get_evidence_list_for_agent\` 附近添加:
\`\`\`python
async def aget_evidence_list_for_agent(
    self, case_id: str, ownership: str = "all"
) -> list[dict[str, Any]]:
    """异步版本：获取证据列表供 Agent 使用。"""
    from asgiref.sync import sync_to_async
    items = await sync_to_async(
        get_evidence_query_service().list_evidence_items_for_case_internal
    )(case_id, ownership=ownership)
    return [self._format_evidence_item(item) for item in items]
\`\`\`

如果有 \`get_legal_basis_for_agent\` 方法，也添加 async 版本:
\`\`\`python
async def aget_legal_basis_for_agent(self, case_id: str) -> dict[str, Any]:
    """异步版本。"""
    from asgiref.sync import sync_to_async
    # 读取原方法逻辑，用 sync_to_async 包装内部同步调用
    ...
\`\`\`

注意: 复用原方法中的内部逻辑（如 _format_case_info），只是把外层服务调用包上 sync_to_async。

### Step 3: tools.py — 为 4 个 tool 添加 async_func

找到每个 @tool 装饰器，添加 async_func 参数:

对于 \`get_case_info\`:
\`\`\`python
async def _get_case_info_async(case_id: str, **kwargs):
    from apps.litigation_ai.services.session.context_service import LitigationContextService
    return await LitigationContextService().aget_case_info_for_agent(case_id)

@tool(name="get_case_info", description="...", async_func=_get_case_info_async)
def get_case_info(case_id: str, **kwargs):
    ...
\`\`\`

同样处理 \`get_evidence_list\`、\`search_evidence\`、\`get_recommended_document_types\`。

对于 \`search_evidence\`，先 Read evidence_digest_service.py 看是否有 async 版本。如果没有，用 sync_to_async 包装。

### Step 4: draft_service.py — 使用已有的 async 版本

找到 line ~91:
\`\`\`python
case_info = await sync_to_async(context_service.build_case_info)(case_id, document_type)
\`\`\`
改为:
\`\`\`python
case_info = await context_service.abuild_case_info(case_id, document_type)
\`\`\`

检查 evidence_rag_service.py 是否有 \`aretrieve\`。如果有，line ~114-115:
\`\`\`python
await sync_to_async(rag.ensure_ingested)(rag_ids)
retrieved = await sync_to_async(rag.retrieve)(...)
\`\`\`
改为:
\`\`\`python
await rag.aensure_ingested(rag_ids)  # 如果有 async 版本
retrieved = await rag.aretrieve(...)  # 如果有 async 版本
\`\`\`
如果没有 async 版本，保持 sync_to_async 但添加注释说明。

### Step 5: evidence_rag_service.py — 添加 async 版本（如果不存在）

如果有 \`aretrieve\` 但没有 \`aensure_ingested\`，添加:
\`\`\`python
async def aensure_ingested(self, evidence_ids: list[str]) -> None:
    """异步版本：确保证据已入库。"""
    from asgiref.sync import sync_to_async
    await sync_to_async(self.ensure_ingested)(evidence_ids)
\`\`\`

## 注意事项
1. 保持原有同步版本不变
2. sync_to_async 包装是可接受的临时方案，因为底层 service 是同步的
3. 不要修改 litigation_consumer.py（已经是正确的）
4. 不要修改 session_repository.py（已有完整双 API）
5. 验证: \`cd backend && python manage.py check\`
6. commit: \`perf(litigation_ai): async 化 agent tools + context service + draft service\``,
  { label: 'fix:step3-litigation', phase: 'Fix', model: 'opus' }
)

log('✅ Step 3 完成')
return { step: 3, result: 'done', details: result }
