export const meta = {
  name: 'async-fix-step2-story-viz',
  description: 'Step 2: async 化 story_viz LLM 调用链',
  phases: [
    { title: 'Fix', detail: 'story_viz P0 修复', model: 'opus' },
  ],
}

log('🔧 Step 2: async 化 story_viz LLM 调用链')

const result = await agent(
  `你是 Django async 修复专家。story_viz 模块的 LLM 调用链全同步，需要 async 化。

## 背景
- \`LLMService\`（在 \`backend/apps/core/llm/service.py\`）已有 \`achat()\` 方法，签名与 \`chat()\` 一致
- 3 个 service（fact_extraction, animation_script, svg_fragment_generator）都通过 \`self._llm_service.chat(...)\` 同步调用
- workflow_service 串联这 3 个 service，也是同步的
- 任务入口在 \`backend/apps/story_viz/tasks.py\`，通过 Celery/Django-Q 触发

## 修复步骤

### Step 1: 读取所有相关文件
先 Read 这些文件了解完整上下文：
- \`backend/apps/story_viz/services/fact_extraction_service.py\`
- \`backend/apps/story_viz/services/animation_script_service.py\`
- \`backend/apps/story_viz/services/svg_fragment_generator_service.py\`
- \`backend/apps/story_viz/services/workflow_service.py\`
- \`backend/apps/story_viz/tasks.py\`

### Step 2: 为 3 个 service 添加 async 版本

**fact_extraction_service.py:**
在 \`extract\` 方法附近添加:
\`\`\`python
async def aextract(self, raw_text: str) -> ExtractedFacts:
    """异步版本，使用 achat 替代 chat。"""
    prompt = self._build_prompt(raw_text)
    messages = [{"role": "user", "content": prompt}]
    try:
        llm_resp = await self._llm_service.achat(messages=messages, model=self._model, temperature=0.0)
        return self._parse_response(llm_resp.content)
    except Exception:
        try:
            llm_resp = await self._llm_service.achat(messages=messages, model=self._model, temperature=0.3)
            return self._parse_response(llm_resp.content)
        except Exception:
            return self._build_fallback_facts(raw_text)
\`\`\`
注意: 保持与 \`extract\` 完全相同的逻辑，只把 \`chat\` 改为 \`achat\`，\`def\` 改为 \`async def\`。

**animation_script_service.py:**
在 \`generate_script\` 方法附近添加:
\`\`\`python
async def agenerate_script(self, facts: ExtractedFacts) -> AnimationScript:
    """异步版本，使用 achat 替代 chat。"""
    prompt = self._build_prompt(facts)
    messages = [{"role": "user", "content": prompt}]
    try:
        llm_resp = await self._llm_service.achat(messages=messages, model=self._model, temperature=0.0)
        return self._parse_response(llm_resp.content)
    except Exception:
        try:
            llm_resp = await self._llm_service.achat(messages=messages, model=self._model, temperature=0.3)
            return self._parse_response(llm_resp.content)
        except Exception:
            return self._build_fallback_script(facts)
\`\`\`

**svg_fragment_generator_service.py:**
在 \`generate\` 方法附近添加:
\`\`\`python
async def agenerate(self, script: AnimationScript) -> list[SVGFragment]:
    """异步版本，使用 achat 替代 chat。"""
    prompt = self._build_prompt(script)
    messages = [{"role": "user", "content": prompt}]
    try:
        llm_resp = await self._llm_service.achat(messages=messages, model=self._model, temperature=0.0)
        return self._parse_response(llm_resp.content)
    except Exception:
        return self._fallback_fragments(script)
\`\`\`

### Step 3: 为 workflow 添加 async 版本

**workflow_service.py:**
在 \`run\` 方法附近添加:
\`\`\`python
async def arun(self, *, animation_id: int) -> None:
    """异步版本的工作流，所有 LLM 调用使用 async。"""
    # 从 DB 获取动画对象（async ORM）
    from apps.story_viz.models import StoryAnimation
    animation = await StoryAnimation.objects.aget(id=animation_id)

    try:
        animation.status = "processing"
        await animation.asave(update_fields=["status"])

        # Step 1: 预处理（纯逻辑，无需 async）
        preprocessed = self._preprocess_service.preprocess(raw_text=animation.raw_text)

        # Step 2: 提取事实（async LLM）
        if self._cancel_requested(animation):
            return
        facts = await self._fact_service.aextract(preprocessed.cleaned_text)

        # Step 3: 生成脚本（async LLM）
        if self._cancel_requested(animation):
            return
        script = await self._script_service.generate_script(facts)

        # Step 4: 渲染（纯逻辑）
        rendered = self._renderer_service.render(script)

        # Step 5: 生成 SVG 片段（async LLM）
        if self._cancel_requested(animation):
            return
        fragments = await self._fragment_service.agenerate(script)

        # Step 6: 合成（纯逻辑）
        result = self._composer_service.compose(rendered, fragments)

        animation.status = "completed"
        animation.result = result
        await animation.asave(update_fields=["status", "result"])

    except Exception as exc:
        animation.status = "failed"
        animation.error_message = str(exc)
        await animation.asave(update_fields=["status", "error_message"])
        raise
\`\`\`
注意: 仔细阅读原始 \`run\` 方法中的所有逻辑，确保 async 版本完整覆盖。_cancel_requested 如果内部用了 ORM，也需要 async 化（或者用 sync_to_async 包装）。

### Step 4: 添加 async task 入口

**tasks.py:**
在现有的 \`generate_story_animation\` task 附近添加:
\`\`\`python
async def agenerate_story_animation(animation_id: int) -> None:
    """异步版本的 task 入口。"""
    from apps.story_viz.services.wiring import get_story_animation_workflow_service
    workflow = get_story_animation_workflow_service()
    await workflow.arun(animation_id=animation_id)
\`\`\`
如果现有的 task 是 Celery @shared_task，保持它不变（Celery 不直接支持 async task）。新添加的 async 版本供其他 async 调用方使用。

## 重要注意事项
1. 先 Read 每个文件了解完整上下文
2. 保持原有同步版本不变（向后兼容）
3. 只添加 async 版本（a-prefixed 方法）
4. 使用 Edit 工具精确修改
5. 修改完成后验证: \`cd backend && python manage.py check\`
6. commit: \`perf(story_viz): async 化 LLM 调用链（fact/script/svg/workflow）\``,
  { label: 'fix:step2-story-viz', phase: 'Fix', model: 'opus' }
)

log('✅ Step 2 完成')
return { step: 2, result: 'done', details: result }
