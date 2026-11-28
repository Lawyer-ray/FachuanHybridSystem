/**
 * 技能正文的字节数口径与两档提示。
 *
 * 为什么量字节而不是量字符：两个上限都是**字节**，且中文正文一个汉字 3 字节——
 * 按字符数提示会让律师在「才 5 千字」时被 422 挡住。
 *
 * - 16000 字节 = MCP `get_agent_skill` 单次读取上限（CONTRACT §8 的 `limit=16000`）：
 *   超过就得分段读，AI 这一轮看到的是片段而不是全文，所以是**柔和提示**；
 * - 32768 字节 = 后端写入口硬上限（`constants.MAX_BODY_BYTES`）：超了提交直接 422，
 *   必须标红说清「会失败」，不能等保存时才报错。
 */

/** 单次按需读取的上限（字节） */
export const SKILL_BODY_SEGMENT_BYTES = 16_000
/** 正文字段硬上限（字节），与后端 `MAX_BODY_BYTES` 同值 */
export const SKILL_BODY_MAX_BYTES = 32_768

export type SkillBodySizeLevel = 'ok' | 'segment' | 'over'

export interface SkillBodyMeasurement {
  /** UTF-8 字节数（`TextEncoder` 与后端 `encode('utf-8')` 同口径） */
  bytes: number
  level: SkillBodySizeLevel
  /** 空串 = 不用提示（额度内只说字节数） */
  hint: string
}

/** UTF-8 字节数；换行也按 `\n` 的 1 字节算，与后端落库口径一致 */
export function byteLength(text: string): number {
  return new TextEncoder().encode(text).length
}

export function skillBodySize(body: string): SkillBodyMeasurement {
  const bytes = byteLength(body)
  if (bytes > SKILL_BODY_MAX_BYTES) {
    return { bytes, level: 'over', hint: `超过 32KB，提交会被拒绝（上限 ${SKILL_BODY_MAX_BYTES} 字节）` }
  }
  if (bytes > SKILL_BODY_SEGMENT_BYTES) {
    return { bytes, level: 'segment', hint: '超过 16KB 后，AI 按需读取会分段' }
  }
  return { bytes, level: 'ok', hint: '' }
}
