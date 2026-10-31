/**
 * 银行批量诉讼的小工具（纯函数，无 React 依赖）。
 *
 * 为什么单独一个文件而不是塞进组件：组件文件只能导出组件（react-refresh 约束，
 * 见 CaseListPage 的 lint 报错）。金额格式化与 mbid 推断都会被多个组件用，
 * 放在组件文件里会让 fast-refresh 失效。
 */

/**
 * 金额千分位。
 *
 * ⚠️ 不要用 `Number(v).toLocaleString()`：后端返的是 Decimal 序列化后的字符串，
 * 转 Number 在千万级金额上会丢精度 —— 而这些金额是要递法院的。
 * 这里只做字符串切分，全程不经过浮点。
 */
export function fmtMoney(v: string | number | null | undefined): string {
  if (v == null) return '—'
  const s = String(v)
  const [int = '', dec] = s.split('.')
  const withComma = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return dec ? `${withComma}.${dec}` : withComma
}

/**
 * 按案由推断要素式文书的 mbid。
 *
 * 只是**默认值**，律师可在下拉框改。故意用最保守的匹配：
 * 认不出就回落到金融借款起诉状（本场景的主案由），而不是空。
 */
export function suggestMbid(cause: string | null | undefined): string {
  const c = cause ?? ''
  if (/民间借贷/.test(c)) return 'mjjdqsz'
  if (/买卖合同/.test(c)) return 'lhjfqsz'
  if (/信用卡/.test(c)) return 'xykqsz'
  if (/金融借款|借款合同/.test(c)) return 'jrjkqsz'
  return 'jrjkqsz'
}
