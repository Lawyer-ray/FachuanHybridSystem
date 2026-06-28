export const meta = {
  name: 'async-fix-step6-docs-workbench-misc',
  description: 'Step 6: async 化 documents + workbench + 杂项 P1',
  phases: [{ title: 'Fix', model: 'opus' }],
}

log('🔧 Step 6: async 化 documents + workbench + misc P1')

const result = await agent(
  `你是 Django async 修复专家。修复 documents、workbench 及其他模块的 P1 问题。

## 任务 A: documents — CPU 密集操作 asyncio.to_thread

### A1: pdf_merge_utils.py
Read \`backend/apps/documents/services/infrastructure/pdf_merge_utils.py\`
- \`convert_docx_to_pdf\` 使用 \`subprocess.run\` 阻塞最长 60 秒
- 添加 async 版本:
  \`\`\`python
  async def aconvert_docx_to_pdf(input_path: str, output_path: str) -> str:
      return await asyncio.to_thread(convert_docx_to_pdf, input_path, output_path)
  \`\`\`

### A2: analysis_service.py
Read \`backend/apps/documents/services/external_template/analysis_service.py\`
- 已有 \`analyze_template_async\` 使用 \`asyncio.to_thread\`，检查是否正确
- 如果 LLM 调用仍同步，标记但不改（优先级低）

### A3: litigation_llm_generator.py
Read \`backend/apps/documents/services/generation/litigation_llm_generator.py\`
- 同步 LLM HTTP 调用
- 添加 async 版本使用已有的 \`LLMService.achat()\`

## 任务 B: workbench — async 化

### B1: batch_runner.py
Read \`backend/apps/workbench/tasks/batch_runner.py\`
- 找到 \`_sync_llm_chat\` 中的 \`time.sleep\`
- 如果在 ThreadPoolExecutor 中运行（通过 run_in_executor），改为:
  - 用 \`asyncio.sleep\` 替代 \`time.sleep\`（如果改为 async）
  - 或保持 \`time.sleep\`（如果必须同步执行）
- 找到 \`_run_batch_async\` 中的 \`sync_to_async\` 包装 ORM:
  - 如果有 23 处 \`sync_to_async(.objects.filter().update())\` 链
  - 用原生 async ORM 替换: \`await Model.objects.filter(...).aupdate(...)\`

### B2: doc_extractor.py
Read \`backend/apps/workbench/services/doc_extractor.py\`
- 已有 \`batch_convert_doc_to_docx_async\`（line ~183）
- 找到调用同步版本的地方，切换为 async 版本

### B3: agents/definitions.py
Read \`backend/apps/workbench/agents/definitions.py\`
- \`_build_agent\` 中创建 \`httpx.AsyncClient\` 但未关闭
- 修复: 确保 client 有 lifecycle 管理（存储引用 + 清理方法）

## 任务 C: docspace — async HTTP

Read \`backend/apps/docspace/services/docspace_client.py\`
- 6 个同步方法: upload_file, create_empty_docx, get_file_info, list_files, download_file, delete_file
- 添加对应的 async 版本:
  \`\`\`python
  async def aupload_file(self, ...) -> dict:
      async with httpx.AsyncClient(...) as client:
          resp = await client.post(...)
          return resp.json()
  \`\`\`

## 任务 D: 其他 P1

### D1: image_rotation
Read \`backend/apps/image_rotation/api/image_rotation_api.py\`
- \`export_pdf\` 是 CPU+IO 密集同步视图
- 改为 \`async def\` + \`asyncio.to_thread(export_as_pdf, ...)\`

### D2: chat_records
Read \`backend/apps/chat_records/api/chat_records_api.py\`
- \`stream_recording\` 使用 Django StreamingHttpResponse（必须同步）
- 标记为「保持同步，Django StreamingHttpResponse 不支持 async」
- 无需修改

### D3: legal_research
Read \`backend/apps/legal_research/api/legal_research_api.py\`
- \`check_law_references\` 使用 \`loop.run_in_executor\` 执行同步 HTTP
- 将内部的威科先行 API 调用改为 \`httpx.AsyncClient\`:
  - 搜索内部的 \`requests.get/post\` 调用
  - 改为 \`async with httpx.AsyncClient() as client: resp = await client.get/post(...)\`
  - 移除外层的 \`run_in_executor\` 包装

### D4: pdf_splitting
Read \`backend/apps/pdf_splitting/services/split/service.py\`
- \`analyze_job\` 中 \`_update_progress\` 循环内 ORM update
- 改为: 累积更新，每 N 页批量 update 一次，或用 Redis 缓存进度

### D5: workflow template_api
Read \`backend/apps/workflow/api/template_api.py\`
- 同步视图 + ORM，改为 \`async def\` + async ORM

## 注意事项
1. 先 Read 每个文件
2. StreamingHttpResponse 必须保持同步（Django 限制）
3. CPU 密集操作用 \`asyncio.to_thread()\` 包裹
4. 验证: \`cd backend && python manage.py check\`
5. commit: \`perf(documents,workbench,misc): async 化文件处理 + LLM 调用\``,
  { label: 'fix:step6-docs-workbench-misc', phase: 'Fix', model: 'opus' }
)

log('✅ Step 6 完成')
return { step: 6, result: 'done', details: result }
