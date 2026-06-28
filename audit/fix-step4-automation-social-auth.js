export const meta = {
  name: 'async-fix-step4-automation-social-auth',
  description: 'Step 4: async 化 automation 平台对接 + social_auth 登录',
  phases: [{ title: 'Fix', model: 'opus' }],
}

log('🔧 Step 4: async 化 automation + social_auth')

const result = await agent(
  `你是 Django async 修复专家。修复 automation 和 social_auth 模块的 P1 问题。

## 任务 A: automation — 切换到已有 async 文件上传

以下 4 个文件有同步 HTTP 调用，但每个都已有 async 版本。你需要找到调用同步版本的代码路径，确保它们使用 async 版本。

1. Read \`backend/apps/automation/services/chat/_dingtalk_file_mixin.py\`
   - \`_upload_media\` (sync, line ~81) 已有 \`_aupload_media\` (async, line ~170)
   - 找到调用 \`_upload_media\` 的地方，检查是否在 async 上下文中
   - 如果调用方是 async，改为调用 \`await self._aupload_media(...)\`

2. Read \`backend/apps/automation/services/chat/_feishu_file_mixin.py\`
   - \`_upload_file\` (sync) 已有 \`_aupload_file\` (async)
   - 同上处理

3. Read \`backend/apps/automation/services/chat/_telegram_file_mixin.py\`
   - \`_send_document\` (sync) 已有 \`_asend_document\` (async)
   - 同上处理

4. Read \`backend/apps/automation/services/chat/_wechat_work_file_mixin.py\`
   - \`_upload_temp_material\` (sync) 已有 \`_aupload_temp_material\` (async)
   - 同上处理

5. Read 调用方来确定上下文:
   - 搜索这些方法被谁调用（Grep 搜索函数名）
   - 如果调用方在 async 方法中，切换到 async 版本
   - 如果调用方在同步 worker 中，保持同步版本

## 任务 B: social_auth — async ORM 化

### B1: social_auth_service.py
Read \`backend/apps/social_auth/services/social_auth_service.py\`

找到 \`_ensure_unique_username\` 方法:
- 改为 \`async def\`
- 将 \`Lawyer.objects.filter(username=base).exists()\` 改为 \`await Lawyer.objects.filter(username=base).aexists()\`
- 循环中的 \`exists()\` 也改为 \`aexists()\`

找到 \`link_or_create_user\` 方法:
- 改为 \`async def\`
- 将 \`@transaction.atomic\` 改为使用 \`async with contextlib.asynccontextmanager(...)\` 或保持在外部
- ORM 调用改为 async 版本:
  - \`SocialAccount.objects.select_related(...).filter(...).first()\` → \`await SocialAccount.objects.select_related(...).filter(...).afirst()\`
  - \`.save()\` → \`await .asave()\`
  - \`Lawyer.objects.create(...)\` → \`await Lawyer.objects.acreate(...)\`
  - \`SocialAccount.objects.create(...)\` → \`await SocialAccount.objects.acreate(...)\`

### B2: social_auth_api.py
Read \`backend/apps/social_auth/api/social_auth_api.py\`

找到 \`token_exchange\` 视图:
- 改为 \`async def\`
- \`TempAuth.objects.select_related('user').get(...)\` → \`await TempAuth.objects.select_related('user').aget(...)\`
- \`temp.delete()\` → \`await temp.adelete()\`

### B3: 检查所有调用方
- Grep 搜索 \`link_or_create_user\` 和 \`token_exchange\` 的所有调用方
- 调用方如果是 async 函数，更新为 \`await\`
- 调用方如果是同步函数（如 Celery task），用 \`asyncio.run()\` 或 \`sync_to_async\` 包装

## 注意事项
1. 先 Read 每个文件
2. 保持同步版本向后兼容
3. 验证: \`cd backend && python manage.py check\`
4. commit: \`perf(automation,social_auth): 统一 async 调用路径 + async ORM\``,
  { label: 'fix:step4-automation-social-auth', phase: 'Fix', model: 'opus' }
)

log('✅ Step 4 完成')
return { step: 4, result: 'done', details: result }
