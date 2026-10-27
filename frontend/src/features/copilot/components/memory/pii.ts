/**
 * 策展提升的 PII 粗筛与「原样提升」判定（纯函数，可 node 单测）。
 *
 * 与后端 `_PII_PATTERNS` / `content_hash_of` 同源的**粗筛**，只用于改写框的即时
 * 提示：真正拒绝在后端。放在这里而不是对话框里，是为了能脱离 DOM 单测。
 */

/** 与后端 `_PII_PATTERNS` 同源的粗筛，只用于即时提示 */
export const PII_RULES: { label: string; pattern: RegExp }[] = [
  { label: '身份证号', pattern: /\b\d{17}[\dXx]\b/ },
  { label: '手机号', pattern: /\b1[3-9]\d{9}\b/ },
  { label: '案号', pattern: /[（(]\s*\d{4}\s*[）)]\s*[\u4e00-\u9fa5]{0,4}\d{1,8}[\u4e00-\u9fa5]*\d*号/ },
  { label: '银行卡号', pattern: /\b\d{16,19}\b/ },
  { label: '完整当事人名称', pattern: /[\u4e00-\u9fa5]{4,20}(?:有限公司|有限责任公司|股份有限公司|事务所|中心|厂)/ },
]

/** 命中的敏感模式名（空数组 = 没命中） */
export function scanPii(text: string): string[] {
  return PII_RULES.filter((rule) => rule.pattern.test(text)).map((rule) => rule.label)
}

/** 归一化对比：与后端 `content_hash_of` 同口径，判断是否「原样提升」 */
export function normalize(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(' ')
}
