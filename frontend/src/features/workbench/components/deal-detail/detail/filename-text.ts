/**
 * 文件名展示形：括号内内容一律隐藏（案件背景、当事人、年份都不留——
 * 案件名在卡片上已有，全名悬停 tooltip / 预览面板可见）。
 * 「告知书（张某诉某公司买卖合同纠纷一案）_收.pdf」→「告知书_收.pdf」；
 * 「通知书（王某执行案）」→「通知书」。整名都在括号里、或隐藏后只剩
 * 扩展名时退回原名。扫描而非正则：案件名里常嵌公司名括号（如
 * 「诉某公司（广东）分公司」），需配平。
 */
export function stripEntryParens(name: string): string {
  let out = ''
  let i = 0
  while (i < name.length) {
    const ch = name[i]
    if (ch !== '（' && ch !== '(') {
      out += ch
      i++
      continue
    }
    const open = ch
    const close = ch === '（' ? '）' : ')'
    let depth = 1
    let j = i + 1
    while (j < name.length && depth > 0) {
      if (name[j] === open) depth++
      else if (name[j] === close) depth--
      j++
    }
    if (depth !== 0) {
      out += name.slice(i) // 括号不配对：余下原样保留
      break
    }
    i = j
  }
  const stripped = out.replace(/\s{2,}/g, ' ').trim()
  if (!stripped) return name
  const stem = stripped.replace(/\.[^.]+$/, '').trim()
  return stem ? stripped : name
}

/**
 * 附件 chip 的短名：去掉扩展名与第一个「_」起的尾巴。
 * 生成文书的命名是「{文书名}_{委托人相关标识}.ext」（如
 * 民事诉讼风险提示书_test_贵州省山地智能….pdf），chip 只显示文书名——
 * 时间轴里委托人就是本案当事人，尾巴是纯噪音；完整名 hover title 可见。
 * 无下划线的名字只去扩展名；截断后为空（名字以 _ 开头）回退原全名。
 */
export function shortDocName(name: string): string {
  const noExt = name.replace(/\.[a-z0-9]{1,6}$/i, '')
  const cut = noExt.indexOf('_')
  if (cut <= 0) return cut === 0 ? name : noExt
  return noExt.slice(0, cut)
}

/** 日志正文按 URL 切段：text 段原样，url 段渲染成「查看链接」超链接——
 * 法院短信里的送达链接动辄 200+ 字符的 query 串，整串显示既撑版面又没法点。
 * URL 字符集排除 CJK 与中英文括号/句读：短信里链接常紧贴中文，\S 会把
 * 后续文字吞进 URL。
 */
const URL_RE = /https?:\/\/[^\s<>"'(),;!()\u4e00-\u9fff\u3000-\u303f\uff01-\uff5e]+/g

export type TextSegment = { kind: 'text'; value: string } | { kind: 'url'; value: string }

export function splitLinkText(text: string): TextSegment[] {
  const segments: TextSegment[] = []
  let last = 0
  for (const m of text.matchAll(URL_RE)) {
    const idx = m.index ?? 0
    if (idx > last) segments.push({ kind: 'text', value: text.slice(last, idx) })
    segments.push({ kind: 'url', value: m[0] })
    last = idx + m[0].length
  }
  if (last < text.length) segments.push({ kind: 'text', value: text.slice(last) })
  return segments
}
