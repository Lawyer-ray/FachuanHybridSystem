export const meta = {
  name: 'async-fix-step1-core',
  description: 'Step 1: async 化 core conversation_history 全链路 + McpToolClient',
  phases: [
    { title: 'Fix', detail: '修复 core + enterprise_data P0', model: 'opus' },
    { title: 'Verify', detail: '验证改动', model: 'opus' },
  ],
}

log('🔧 Step 1: 修复 core conversation_history 全链路 + McpToolClient')

const fixResult = await agent(
  `你是一个 Django async 修复专家。请按照以下精确指令修改代码。

## 任务 1: conversation_history 全链路 async 化

### 1a. 仓库层 — 添加 async 查询方法
文件: \`backend/apps/core/repositories/conversation_repository.py\`
- 在已有的 \`acreate\` / \`adelete_by_session_id\` 附近添加:
  \`\`\`python
  async def aget_by_session_id(self, session_id: str) -> QuerySet[ConversationHistory]:
      return ConversationHistory.objects.filter(session_id=session_id)
  \`\`\`
  注意: 返回 QuerySet 本身不触发 I/O，调用方需要用 async 方式遍历（如 \`async for\` 或 \`[r async for r in qs]\` 或 \`await qs.alist()\`（Django 4.1+ 无 alist，需要用 sync_to_async(list)(qs) 或 async for）。

### 1b. Service 层 — 添加 async 方法
文件: \`backend/apps/core/services/conversation_history_service.py\`
- 在 \`get_conversation_history_messages\` 方法附近添加:
  \`\`\`python
  async def aget_conversation_history_messages(
      self,
      *,
      session_id: str,
      user_id: str | None = None,
      limit: int = 50,
  ) -> list[dict[str, Any]]:
      qs = self._repository.get_by_session_id(session_id)
      if user_id:
          qs = qs.filter(user_id=user_id)
      qs = qs.order_by("-created_at")[:limit]
      history = [record async for record in qs]

      messages: list[dict[str, Any]] = []
      for record in reversed(history):
          messages.append(
              {
                  "role": record.role,
                  "content": record.content,
                  "created_at": record.created_at.isoformat(),
                  "metadata": record.metadata,
              }
          )
      return messages
  \`\`\`
  注意: Django QuerySet slice 后仍然可以 async iterate（\`__aiter__\` 在 QuerySet 上可用）。

### 1c. 桥接层 — 添加 async 函数
文件: \`backend/apps/core/api/llm_common.py\`
- 在 \`get_conversation_history\` 函数附近添加:
  \`\`\`python
  async def aget_conversation_history(session_id: str, user_id: str | None = None, limit: int = 50) -> dict[str, Any]:
      service = _get_conversation_history_service()
      messages = await service.aget_conversation_history_messages(session_id=session_id, user_id=user_id, limit=limit)
      return {"session_id": session_id, "messages": messages}
  \`\`\`
- 更新 import 在文件顶部，确保 aget_conversation_history 能被外部导入

### 1d. API 层 — 视图改 async
文件: \`backend/apps/core/api/ninja_llm_api.py\`
- 找到 \`get_conversation_history\` 视图函数（line ~157）
- 将 \`def get_conversation_history\` 改为 \`async def get_conversation_history\`
- 将 \`result = get_conversation_history_impl(...)\` 改为 \`result = await aget_conversation_history(...)\`
- 更新 import: 从 llm_common 导入 \`aget_conversation_history\` 而非 \`get_conversation_history_impl\`

## 任务 2: McpToolClient 添加 async 方法

文件: \`backend/apps/enterprise_data/services/clients/mcp_tool_client.py\`
- 找到 \`call_tool\` 方法（line ~99）
- 在其附近添加:
  \`\`\`python
  async def acall_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
      """异步版本的 call_tool，直接 await _call_tool_async，避免 run_coroutine_threadsafe 阻塞。"""
      self._acquire_rate_limit(action=f"call_tool:{tool_name}")
      started = time.perf_counter()
      result, execution_meta = await self._aexecute_with_api_key_failover(
          action=f"call_tool:{tool_name}",
          operation=lambda api_key, transport: self._call_tool_async(
              transport=transport, tool_name=tool_name, arguments=arguments, api_key=api_key,
          ),
          log_context={"tool": tool_name},
      )
      elapsed_ms = (time.perf_counter() - started) * 1000
      logger.info("MCP tool %s completed in %.1fms", tool_name, elapsed_ms)
      return result
  \`\`\`
- 检查是否有 \`_aexecute_with_api_key_failover\` 方法。如果没有，需要参考 \`_execute_with_api_key_failover\` 创建 async 版本:
  - 将 \`run_coroutine_threadsafe(...).result()\` 替换为直接 \`await\`
  - 保持重试/failover 逻辑

## 重要注意事项
1. 先 Read 每个文件了解完整上下文，再做修改
2. 使用 Edit 工具精确修改，不要重写整个文件
3. 修改完成后，运行 \`cd backend && python manage.py check\` 验证
4. commit 格式: \`perf(core,enterprise_data): async 化 conversation_history 全链路 + McpToolClient\`
`,
  { label: 'fix:step1-core', phase: 'Fix', model: 'opus' }
)

log('✅ Step 1 完成')
return { step: 1, result: 'done', details: fixResult }
