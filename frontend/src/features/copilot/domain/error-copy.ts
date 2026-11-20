/**
 * 旧后端的**文案 → 归属**兜底表（没有 code 时的唯一分类手段）。
 *
 * 为什么单独一个文件：这是一张纯数据表，**会一直留着**——灰度/回滚期间线上仍有
 * 只发 `message` 的后端实例，那些实例的错误只能按文案认。它和 `error.ts` 的
 * 「分类/诊断/动作」逻辑寿命不同：表随后端文案变，逻辑随交互变，混在一个文件里
 * 谁也说不清改一行会波及什么（第一版就是表 + 逻辑 + 组件文案三段混在一起）。
 *
 * 维护约定（改文案必须同步这里）：
 * - `match` 就是 store 各处 `set({ lastError })` 的原文片段，用 `includes` 匹配；
 * - `kind` 决定图标分色，`code` 决定**有没有动作按钮**。没有一一对应 code 的条目
 *   一律写 `'unknown'`：宁可少一个按钮，也不要给一个点了没用的按钮
 *   （例如「只跑了主后端」写 capability_unsupported 会推出「换个后端」，而席位满
 *   换哪个后端都是满的；「压缩失败」写 context_exceeded 会推出「压缩上下文」，
 *   点下去拿同一句失败回来）。
 */

import type { ErrorCode, ErrorKind, ErrorSeverity } from './error-codes'

/** 一行文案兜底：`match` 命中后用它的 kind/code/severity/hint */
export interface KnownTextEntry {
  match: string
  kind: ErrorKind
  code: ErrorCode
  severity: ErrorSeverity
  hint: string
  resendable: boolean
}

/** 键是 `store` 各处实际写入的原文（旧后端没有 code，只能靠它） */
export const KNOWN: KnownTextEntry[] = [
  {
    match: '连接中断',
    kind: 'network',
    code: 'backend_unavailable',
    severity: 'error',
    hint: '检查网络后，把刚才那句原样再发一次即可；已生成的部分回答仍在会话里。',
    resendable: true,
  },
  {
    match: '连接提前结束',
    kind: 'stream_broken',
    code: 'upstream_timeout',
    severity: 'warn',
    hint: '上游提前断开了，回答可能不完整。可以重发，或在会话里追问「继续说」。',
    resendable: true,
  },
  {
    match: '创建会话失败',
    kind: 'network',
    code: 'backend_unavailable',
    severity: 'error',
    hint: '通常是网络或网关抖动，重发一次即可（不会产生重复会话）。',
    resendable: true,
  },
  {
    match: '加载会话历史失败',
    kind: 'history',
    code: 'unknown',
    severity: 'warn',
    hint: '历史没拉下来，但可以继续问；切到别的会话再切回来会重试一次。',
    resendable: false,
  },
  {
    match: '当前使用人数较多',
    kind: 'rate_limited',
    code: 'rate_limited',
    severity: 'warn',
    hint: '这是排队限流，不是你的问题。等十几秒再试。',
    resendable: true,
  },
  {
    match: '本轮对话已结束',
    kind: 'turn_ended',
    code: 'unknown',
    severity: 'info',
    hint: '插话只在生成过程中生效；本轮已经跑完，直接发新消息就是新一轮。',
    resendable: false,
  },
  {
    // 注意：**不**映射成 capability_unsupported。降级是并发席位满导致的，换后端
    // 解决不了（换了还是满），映射过去会多出一个点了没用的「换个后端」按钮。
    match: '只跑了主后端',
    kind: 'capability',
    code: 'unknown',
    severity: 'info',
    hint: '并发席位满了，本轮只跑了主后端。想要并排对比，等人少时再选多栏。',
    resendable: false,
  },
  {
    match: '附件/引用准备失败',
    kind: 'attachment',
    code: 'unknown',
    severity: 'error',
    hint: '附件还留着，重发不会重复上传；若持续失败，换 PDF/图片以外的格式再试。',
    resendable: true,
  },
  {
    match: '无需压缩',
    kind: 'compact',
    code: 'unknown',
    severity: 'info',
    hint: '当前会话还没有可压缩的历史，这是正常提示，不用处理。',
    resendable: false,
  },
  {
    // 同理不映射成 context_exceeded：这是「压缩这个动作」失败，不是上下文超限，
    // 否则会给一个「压缩上下文」按钮，点下去拿同样一句话回头。
    match: '压缩失败',
    kind: 'compact',
    code: 'unknown',
    severity: 'warn',
    hint: '压缩没成功，上下文水位没变；继续问也可以，接近上限时系统会自动压缩。',
    resendable: false,
  },
  {
    match: '提交后台任务失败',
    kind: 'task',
    code: 'unknown',
    severity: 'error',
    hint: '任务没投递成功，重新提交一次即可。',
    resendable: true,
  },
  {
    match: '插话发送失败',
    kind: 'network',
    code: 'backend_unavailable',
    severity: 'warn',
    hint: '插话没送到模型，可再发一次；或等本轮结束后作为新消息提问。',
    resendable: true,
  },
  {
    match: '撤回插话失败',
    kind: 'network',
    code: 'backend_unavailable',
    severity: 'warn',
    hint: '撤回请求没成功，排队里的插话可能仍会生效。',
    resendable: false,
  },
]
