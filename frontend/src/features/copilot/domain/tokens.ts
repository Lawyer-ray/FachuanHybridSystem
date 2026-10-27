/**
 * 输出速度（tok/s）估算。
 *
 * 后端流式期间只给文本增量；逐 token 计数在每段回答结束的 usage 事件才有。
 * 实时速度用字符启发式估算（展示带 ≈），结束后的总量/平均速度用真实值。
 */

const CJK_RE = /[\u3400-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]/

/** 字符数 → token 估算：CJK ≈ 0.7 token/字（中文优化分词器的常见区间），其余 ≈ 4 字符/token */
export function estimateTokens(text: string): number {
  let cjk = 0
  let other = 0
  for (const ch of text) {
    if (CJK_RE.test(ch)) cjk += 1
    else other += 1
  }
  return Math.round(cjk * 0.7 + other / 4)
}

/** 采样点 [时间, 累计估算 token]；滑动窗口内每秒 token 数 */
export function tokensPerSecond(samples: Array<[number, number]>, now: number, windowMs = 2000): number {
  if (samples.length < 2) return 0
  const last = samples[samples.length - 1]
  if (last === undefined || now < last[0]) return 0
  const windowStart = now - windowMs
  let baseline: [number, number] | undefined
  for (const s of samples) {
    if (s[0] >= windowStart) {
      baseline = s
      break
    }
  }
  if (baseline === undefined || baseline === last) return 0
  const elapsed = (last[0] - baseline[0]) / 1000
  return elapsed > 0 ? (last[1] - baseline[1]) / elapsed : 0
}
