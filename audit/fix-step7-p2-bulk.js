export const meta = {
  name: 'async-fix-step7-p2-bulk',
  description: 'Step 7: P2 批量 async 化 Django Ninja 视图 + 清理 sync_to_async',
  phases: [{ title: 'Fix', model: 'opus' }],
}

log('🔧 Step 7: P2 批量清理')

const result = await agent(
  `你是 Django async 修复专家。进行 P2 批量 async 化清理。

## 总体策略
P2 有 372 个发现，主要分 3 类:
1. **Django Ninja 同步视图** → 改为 \`async def\` + async ORM（可改）
2. **sync_to_async 滥用** → 改为原生 async ORM（可改）
3. **同步 worker 中的代码** → 保持不变（不可改）
4. **Django Admin / Signal handlers** → 保持不变（不可改）

## 工作方式
逐 app 扫描，对每个 app:
1. Grep 搜索所有 Django Ninja 路由定义（\`@router.get\`, \`@router.post\`, \`@router.put\`, \`@router.delete\`）
2. 检查对应的视图函数是 \`def\` 还是 \`async def\`
3. 如果是 \`def\` 且内部有 ORM 操作:
   - 改为 \`async def\`
   - ORM 调用改为 async 版本（\`aget()\`, \`afilter()\`, \`acreate()\`, \`asave()\`, \`adelete()\`）
   - 注意: QuerySet 链式调用需要在最终求值时用 async（如 \`await qs.afirst()\` 或 \`[obj async for obj in qs]\`）
4. 搜索 \`sync_to_async\` 使用:
   - 如果被包装的函数本身可以 async 化，直接改为 async 调用
   - 如果是第三方库的同步代码，保持 sync_to_async

## 按 app 批量处理

### Batch 1: cases
Read \`backend/apps/cases/api/\` 下的 API 文件:
- caseaccess_api.py, caseassignment_api.py, caseparty_api.py, cause_court_api.py 等
- 所有同步视图改为 async def + async ORM
- service 层如果有同步方法被 async 视图调用，添加 async 版本

### Batch 2: contracts + client
- contracts/api/ 下的 CRUD 视图
- client/api/ 下的 CRUD 视图
- 纯计算函数（无 I/O）不需要改

### Batch 3: documents
- documents/api/ 下的 CRUD 视图
- 注意: StreamingHttpResponse 必须保持同步

### Batch 4: batch_printing + chat_records + contacts + doc_convert + doc_converter + docspace
- 各 app 的 API 视图批量改 async
- 文件流式传输（FileResponse/StreamingHttpResponse）保持同步

### Batch 5: organization + oa_filing + finance + evidence + reminders
- 各 app 的 API 视图批量改 async
- 注意 transaction.atomic 在 async 中的用法

### Batch 6: document_parsing + document_recognition + express_query + image_rotation + invoice_recognition
- 各 app 的 API 视图批量改 async

### Batch 7: pdf_splitting + workbench + workflow
- 各 app 的 API 视图批量改 async

### Batch 8: plugins
- plugins/message_hub/api/ 视图改 async
- plugins/court_automation/ 管理后台保持同步

## 具体修改模式

### 模式 A: 同步视图改 async
\`\`\`python
# Before:
@router.get("/items")
def list_items(request):
    items = Item.objects.filter(user=request.user)
    return list(items.values())

# After:
@router.get("/items")
async def list_items(request):
    items = [item async for item in Item.objects.filter(user=request.user).values()]
    return items
\`\`\`

### 模式 B: sync_to_async 替换为原生 async
\`\`\`python
# Before:
data = await sync_to_async(lambda: Model.objects.get(pk=pk))()

# After:
data = await Model.objects.aget(pk=pk)
\`\`\`

### 模式 C: get_object_or_404 替换
\`\`\`python
# Before:
obj = get_object_or_404(Model, pk=pk)

# After:
try:
    obj = await Model.objects.aget(pk=pk)
except Model.DoesNotExist:
    raise Http404
\`\`\`

## 重要限制
1. **不要改** Celery task / Django-Q task 中的代码（同步 worker 需要同步 ORM）
2. **不要改** Django Admin 注册代码
3. **不要改** Django Signal handlers（post_save/pre_save 等）
4. **不要改** pure computation 没有 I/O 的函数
5. **不要改** StreamingHttpResponse / FileResponse 的视图（必须同步）
6. 每改完一个文件，确保 import 正确
7. 不要一次性改太多文件导致冲突，每次改 5-10 个文件后验证

## 注意事项
1. 逐个文件 Read + Edit，不要批量替换
2. 注意 Django ORM async API:
   - QuerySet.filter() 返回的还是 QuerySet，不需要 await
   - 只有最终求值需要 await: .aget(), .acreate(), .asave(), .adelete(), .aexists(), .acount(), .afirst()
   - 遍历 queryset: \`[obj async for obj in qs]\` 或 \`async for obj in qs\`
3. \`transaction.atomic\` 在 async 中: 使用 \`async with transaction.atomic():\` （Django 4.1+）
4. 验证: \`cd backend && python manage.py check\`
5. commit: \`perf(all): P2 批量 async 化 Django Ninja 视图 + 清理 sync_to_async\``,
  { label: 'fix:step7-p2-bulk', phase: 'Fix', model: 'opus' }
)

log('✅ Step 7 完成')
return { step: 7, result: 'done', details: result }
