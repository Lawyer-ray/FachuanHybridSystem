export const meta = {
  name: 'async-fix-step5-core-p1-enterprise',
  description: 'Step 5: async 化 core P1 + enterprise_data P1',
  phases: [{ title: 'Fix', model: 'opus' }],
}

log('🔧 Step 5: async 化 core P1 + enterprise_data P1')

const result = await agent(
  `你是 Django async 修复专家。修复 core 和 enterprise_data 模块的 P1 问题。

## 任务 A: core/llm/model_list_service.py — cache async 化

Read \`backend/apps/core/llm/model_list_service.py\`

找到 \`aget_result\` 方法（line ~207）。它在 async 方法内使用了同步 Django cache:
- \`cache.get(CACHE_KEY)\` → 改为 \`await cache.aget(CACHE_KEY)\`（Django 4.1+ 支持 async cache）
- \`cache.set(CACHE_KEY, ...)\` → 改为 \`await cache.aset(CACHE_KEY, ...)\`

找到 \`_merge_system_config_models\` 方法:
- 如果它调用了同步的 \`LLMConfig._get_system_config()\`，而该方法在检测到 async event loop 后会 fallback:
- 确认是否需要修改，如果 fallback 逻辑正确则保持

## 任务 B: core/llm/config.py — async fallback 修复

Read \`backend/apps/core/llm/config.py\`

找到 \`_get_system_config\` 方法（line ~132）:
- 如果它在检测到 async event loop 后直接 fallback 到 Django settings 而跳过 DB 查询
- 这意味着在 async 上下文中无法从 DB 获取最新配置
- 修复: 使用 sync_to_async 包装 DB 查询，或使用 Django async ORM

## 任务 C: cloud_storage AsyncClient lifecycle

### C1: onedrive_provider.py
Read \`backend/apps/core/cloud_storage/onedrive_provider.py\`

找到 \`_get_async_client\` 方法（line ~299）:
- 问题: \`httpx.AsyncClient\` 创建后存储在 \`self._async_client\` 但没有 close 机制
- 修复:
  - 添加 \`async def aclose(self):\` 方法来关闭 client
  - 或使用 \`async with\` 模式
  - 确保在 provider 生命周期结束时关闭

找到 \`_await_device_code\` 中的 \`time.sleep(5)\`:
- 如果在 async 上下文中调用，改为 \`await asyncio.sleep(5)\`

### C2: webdav_provider.py
Read \`backend/apps/core/cloud_storage/webdav_provider.py\`

同样修复 AsyncClient lifecycle:
- 添加 \`aclose()\` 方法
- 确保 \`httpx.AsyncClient\` 正确关闭
- 将 \`list\` 和 \`upload\` 方法中如果有同步 HTTP 调用改为 async

## 任务 D: enterprise_data MCP provider async 化

Read \`backend/apps/enterprise_data/services/providers/qichacha_mcp.py\`
Read \`backend/apps/enterprise_data/services/providers/tianyancha_mcp.py\`

这些 provider 通过 McpToolClient 调用 MCP。Step 1 已添加了 \`acall_tool\` 方法。

为每个 provider 的同步方法添加 async 版本:
- \`qichacha_mcp.py\`: 为 \`search_company\`, \`get_company_detail\`, \`get_risk_info\` 添加 async 版本，使用 \`await self._client.acall_tool(...)\`
- \`tianyancha_mcp.py\`: 同理

Read \`backend/apps/enterprise_data/services/enterprise_data_service.py\`
- 为 \`query_company_data\` 等高频方法添加 async 版本

## 注意事项
1. 先 Read 每个文件了解上下文
2. Django 4.1+ 的 cache backend 支持 async（aget/aset/adelete）
3. httpx.AsyncClient 必须正确关闭，否则会资源泄漏
4. 验证: \`cd backend && python manage.py check\`
5. commit: \`perf(core,enterprise_data): async 化 LLM cache + 云存储 + MCP provider\``,
  { label: 'fix:step5-core-p1-enterprise', phase: 'Fix', model: 'opus' }
)

log('✅ Step 5 完成')
return { step: 5, result: 'done', details: result }
