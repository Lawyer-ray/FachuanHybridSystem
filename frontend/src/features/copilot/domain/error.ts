/**
 * 错误分类（纯函数）：把 store 里那句 `lastError` 文案翻译成「能不能救、怎么救」。
 *
 * 为什么要分类：`lastError` 是一个字符串，承载了十几种完全不同的情况——建会话
 * 失败、附件上传失败、插话被 409 拒、上下文压缩无事可做、后端降级成单栏……
 * 全部渲染成一行红字的结果是：律师看不出「这条要不要管」，也没法把问题描述清楚
 * 去求助（只能截屏）。
 *
 * 这里**按文案归类而不是改契约**：后端 `error` 事件目前没有稳定错误码，前端各处
 * `set({ lastError })` 的文案是既成事实。按文案映射最轻，且后端将来补 `code`
 * 时可以只改本文件的一处映射（实例化时优先用 `code`）。
 */

/** 错误大类（决定图标颜色与默认建议，不决定具体文案） */
export type ErrorCode =
  | 'network'
  | 'stream_broken'
  | 'rate_limited'
  | 'turn_ended'
  | 'capability'
  | 'attachment'
  | 'compact'
  | 'task'
  | 'history'
  | 'unknown'

export type ErrorSeverity = 'info' | 'warn' | 'error'

export interface ClassifiedError {
  code: ErrorCode
  severity: ErrorSeverity
  /** 展示文案（去掉多答前缀后的原话） */
  message: string
  /** 一句话建议动作（人话，不是按钮） */
  hint: string
  /** 律师可以原样再发一次吗（true 时提示里明说「可直接重发」） */
  resendable: boolean
}

/** 已知文案 → 归类。键是 `store` 各处实际写入的原文（改动文案要同步这里） */
const KNOWN: Array<{
  match: string
  code: ErrorCode
  severity: ErrorSeverity
  hint: string
  resendable: boolean
}> = [
  {
    match: '连接中断',
    code: 'network',
    severity: 'error',
    hint: '检查网络后，把刚才那句原样再发一次即可；已生成的部分回答仍在会话里。',
    resendable: true,
  },
  {
    match: '连接提前结束',
    code: 'stream_broken',
    severity: 'warn',
    hint: '上游提前断开了，回答可能不完整。可以重发，或在会话里追问「继续说」。',
    resendable: true,
  },
  {
    match: '创建会话失败',
    code: 'network',
    severity: 'error',
    hint: '通常是网络或网关抖动，重发一次即可（不会产生重复会话）。',
    resendable: true,
  },
  {
    match: '加载会话历史失败',
    code: 'history',
    severity: 'warn',
    hint: '历史没拉下来，但可以继续问；切到别的会话再切回来会重试一次。',
    resendable: false,
  },
  {
    match: '当前使用人数较多',
    code: 'rate_limited',
    severity: 'warn',
    hint: '这是排队限流，不是你的问题。等十几秒再试。',
    resendable: true,
  },
  {
    match: '本轮对话已结束',
    code: 'turn_ended',
    severity: 'info',
    hint: '插话只在生成过程中生效；本轮已经跑完，直接发新消息就是新一轮。',
    resendable: false,
  },
  {
    match: '只跑了主后端',
    code: 'capability',
    severity: 'info',
    hint: '并发席位满了，本轮只跑了主后端。想要并排对比，等人少时再选多栏。',
    resendable: false,
  },
  {
    match: '附件/引用准备失败',
    code: 'attachment',
    severity: 'error',
    hint: '附件还留着，重发不会重复上传；若持续失败，换 PDF/图片以外的格式再试。',
    resendable: true,
  },
  {
    match: '无需压缩',
    code: 'compact',
    severity: 'info',
    hint: '当前会话还没有可压缩的历史，这是正常提示，不用处理。',
    resendable: false,
  },
  {
    match: '压缩失败',
    code: 'compact',
    severity: 'warn',
    hint: '压缩没成功，上下文水位没变；继续问也可以，接近上限时系统会自动压缩。',
    resendable: false,
  },
  {
    match: '提交后台任务失败',
    code: 'task',
    severity: 'error',
    hint: '任务没投递成功，重新提交一次即可。',
    resendable: true,
  },
  {
    match: '插话发送失败',
    code: 'network',
    severity: 'warn',
    hint: '插话没送到模型，可再发一次；或等本轮结束后作为新消息提问。',
    resendable: true,
  },
  {
    match: '撤回插话失败',
    code: 'network',
    severity: 'warn',
    hint: '撤回请求没成功，排队里的插话可能仍会生效。',
    resendable: false,
  },
]

/**
 * 多答时错误行带 `agent：` 前缀（`pi：xxx`）。归类前剥掉，才能命中已知文案；
 * 剥掉的来源单独返回，用于提示「是哪一栏出错」。
 */
export function splitLanePrefix(raw: string): { lane: string; body: string } {
  const m = /^([\w.-]{1,24})：([\s\S]+)$/.exec(raw.trim())
  if (!m) return { lane: '', body: raw.trim() }
  return { lane: m[1]!, body: m[2]!.trim() }
}

/** 归类一条错误文案；空值返回 null（调用方据此不渲染） */
export function classifyError(raw: string | null | undefined): ClassifiedError | null {
  if (!raw) return null
  const { body } = splitLanePrefix(raw)
  for (const known of KNOWN) {
    if (body.includes(known.match)) {
      return {
        code: known.code,
        severity: known.severity,
        message: body,
        hint: known.hint,
        resendable: known.resendable,
      }
    }
  }
  return {
    code: 'unknown',
    severity: 'error',
    message: body,
    // 未知错误不给空话建议：只说能做什么（复制诊断去反馈）
    hint: '把「复制诊断」的内容发给管理员，能更快定位（含本机时间与错误原文）。',
    resendable: false,
  }
}

/** 诊断文本（复制给管理员）：错误码 + 文案 + 本机时间 */
export function diagnosticsOf(error: ClassifiedError, now = Date.now()): string {
  return [
    `时间：${new Date(now).toISOString()}`,
    `错误码：${error.code}`,
    `原文：${error.message}`,
  ].join('\n')
}
