/**
 * Copilot 纯领域逻辑的统一出口（barrel）。
 *
 * 域内调用方一律 `from './domain'` / `from '../domain'`，不直接引子模块——
 * 这样按职责拆文件对调用点是零改动，后续再调整子模块划分也不会波及全域。
 *
 * 子模块分工：
 * - sse.ts        SSE 帧解析（与 streaming.ts 的帧消费配对）
 * - diff.ts       行级 diff（改写块「改了哪一句」的唯一实现，与 unified diff 同形）
 * - knowledge.ts  入站引用（AI → 材料）：`[Kn]` 角标解析、来源对齐、页标措辞
 * - mention.ts    `@` 引用：token 识别、候选过滤、草稿替换（出站协议仍只有一份）
 * - page-span.ts  工具结果里的 `[page: N]` 页标切分（只在工具结果里用，不进正文）
 * - dual.ts       同题双答：事件的栏归属与栏标签
 * - error.ts      错误文案 → 可操作提示（能否重发、能不能关掉、诊断文本）
 * - progress.ts   流式「还在干活」：当前在调哪个工具、动作词翻译
 * - transcript.ts 转录映射：锚点/引用块的**出站构建 + 回放解析**（成对互逆）
 * - reference.ts  框选引用构建、默认出站提示语、AI 改写落盘识别
 * - approval.ts   审批倒计时窗口（与后端 approval.py 的契约常量）、离线卡映射、状态徽标
 * - attachment.ts 附件预检与大小展示
 * - question.ts   结构化提问（模型反问）：归一化、草稿变换、答案批次
 * - tokens.ts     输出速度估算
 * - usage.ts      用量口径与人读格式化（分栏计量、token/速度/命中率/时长）
 * - slash.ts      `/` 命令菜单
 * - time.ts       转录时间显示（HH:mm）
 * - location.ts   路由 → 页面描述、会话分组
 * - message-id.ts 转录消息 id 解析（db-/local- 两种前缀与「能否评分」）
 * - export.ts     会话导出（Markdown / 纯文本）与文件名
 * - outline.ts    轮次大纲（已加载窗口内的提问 → 回答）
 *
 * 全部为纯函数（无 React、无 IO），vitest 直接覆盖（node 环境，无 DOM）。
 * 唯一例外是 `export.downloadText`：允许触达 Blob/URL/document 的下载动作。
 */

export * from './approval'
export * from './attachment'
export * from './diff'
export * from './knowledge'
export * from './lane-facts'
export * from './mention'
export * from './page-span'
export * from './dual'
export * from './error'
export * from './export'
export * from './location'
export * from './message-id'
export * from './outline'
export * from './progress'
export * from './question'
export * from './reference'
export * from './slash'
export * from './time'
export * from './sse'
export * from './tokens'
export * from './usage'
export * from './transcript'
