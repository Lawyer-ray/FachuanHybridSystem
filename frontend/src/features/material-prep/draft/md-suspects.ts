/**
 * Markdown 可疑点检测：把 OCR 的**确定性错误模式**标出来，交给律师一眼判掉。
 *
 * ═══ 为什么需要它 ═══
 * 律师要靠草稿里的 Markdown 支撑诉讼，而扫描件的 OCR 会稳定地犯几类错——
 * 金额前多一个借贷标记（`D3.00` / `C3159.44`）、日期丢位（`170201` 本该是
 * `20170201`）、表头缺首字（「通借记卡主活期账户交易明细表」）、表格错行。
 * 这些错混在 92 行流水里，肉眼逐行扫必然漏，错数字就直接进了诉状。
 *
 * ═══ 宁可多标，但只多标「可判」的 ═══
 * 金额、日期这类错，误报的代价只是律师一眼「不是问题」；漏报的代价是错数进诉状。
 * 所以它们只抓**最典型形态**，形态一旦对上就不放过。
 * 表头缺字例外：它没有可供一眼判掉的形态（长度切不开 14 字与 15 字），因此只认
 * 结构上能确证的三类（详见 `detectCaptionTruncated`），宁缺勿滥——标记误报一多，
 * 律师就不再看了。
 *
 * ═══ 边界 ═══
 * · 纯函数、纯正则、无模型、无 DOM、无 React —— 任何 UI 可直接调用
 * · 只「指出位置」，不「改内容」：改数要么是模型幻觉，要么是律师的责任
 * · 返回顺序即 markdown 行序；同一行可命中多条
 */

export interface MdSuspect {
  kind: 'amount-prefix' | 'date-short' | 'table-columns' | 'header-truncated' | 'digit-width'
  /** 在 markdown 里的行号（0-based） */
  lineIndex: number
  /** 原始行内容，供 UI 高亮 */
  line: string
  /** 给人看的一句话（中文） */
  hint: string
  severity: 'high' | 'low'
  /** 命中的具体片段 */
  match?: string
}

/** 表格体的一行：行号 + 用 `|` 切开后的单元格（已去首尾空白） */
interface TableRow {
  lineIndex: number
  cells: string[]
}

/** 紧贴表格上方的标题行 */
interface TableCaption {
  lineIndex: number
  text: string
}

/** 一张表：从连续的 `|` 行切出来的一段 */
interface Table {
  rows: TableRow[]
  caption?: TableCaption
}

/** GFM 表格分隔行：`| --- | :--: |` */
const TABLE_RULE = /^\s*\|?(\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$/

/** 金额前混进借贷标记：整格只有 D/C + 数字，如 `D3.00` `C3159.44` `D1,234.56` */
const AMOUNT_PREFIX = /^([DC])(\d[\d,]*\.\d{2})$/

/** 数字单元格：可带千分位、可带负号 */
const NUMBER_CELL = /^-?[\d,]+(\.\d+)?$/

/** 8 位日期的三种写法：紧排 / 点或斜杠分隔 / 短横线分隔 */
const DATE_LONG = [/^\d{8}$/, /^\d{4}[/.]\d{2}[/.]\d{2}$/, /^\d{4}-\d{2}-\d{2}$/]

/** 6 位数字：可能是丢位的日期，也可能本来就是短号 —— 要看同伴才能定 */
const DATE_SHORT = /^\d{6}$/

/**
 * 表头里出现这些词，说明这行在描述资金流水的关键列；
 * 这种表的错行会直接把金额/日期错到别的客户名下，按 high 报。
 */
const FLOW_KEYWORDS = ['日期', '发生额', '余额', '金额', '账号', '卡号', '摘要']

/**
 * 金额类列名：只有这些列下的纯整数格才拿「位数」这把尺去量。
 * 账号 / 卡号列本来就是 16–22 位，用同一个上限去卡会把满表卡号全标成异常。
 */
const AMOUNT_COLUMN_KEYWORDS = ['金额', '发生额', '余额', '利息', '本金', '税额', '罚息', '复利']

/** 金额整数位合理区间：少于 1 位（没有整数部分）或超过 12 位都超出常理 */
const MIN_AMOUNT_INT_DIGITS = 1
const MAX_AMOUNT_INT_DIGITS = 12

/** 表名的合理长度；超过这个长度的是整段正文，不是表名 */
const MAX_CAPTION_CHARS = 80

/** 表名/列名里的口径词 —— 泛用词不算，必须有它才认为这行在说「一列什么」 */
const COLUMN_NOUNS = ['日期', '账号', '卡号', '发生额', '金额', '余额', '摘要', '利率', '户名']

/**
 * 「列名残句」的认定门槛：至少这么多列名词才报。
 * 正文里「日期 金额」这种零星提及是常态，不设门槛会满篇误报。
 */
const MIN_COLUMN_NOUN_HITS = 3

/** 表格至少有这么多列，才算「真表格」——两列的小表与正文难分 */
const MIN_TABLE_COLUMNS = 3

function splitCells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function isTableLine(line: string): boolean {
  return line.trimStart().startsWith('|')
}

function isTableRule(line: string): boolean {
  return TABLE_RULE.test(line)
}

/**
 * 把 markdown 切成一张张表。
 *
 * 表与表之间靠「连续 `|` 行断开」自然分界：跨页续表会重新打一遍列名行，
 * 断成两张表正好各自有表头，互不干扰。表格上方紧贴着的非空行记为标题行。
 */
function collectTables(lines: string[]): Table[] {
  const tables: Table[] = []
  let current: Table | undefined

  for (const [lineIndex, raw] of lines.entries()) {
    const line = raw.trimEnd()
    if (!isTableLine(line)) {
      current = undefined
      continue
    }
    if (!current) {
      current = { rows: [] }
      const above = lines[lineIndex - 1]?.trim() ?? ''
      if (above !== '' && !isTableLine(above)) current.caption = { lineIndex: lineIndex - 1, text: above }
      tables.push(current)
    }
    // 分隔行不参与列数比对，但它上面那行是列名行，要进表体当基准
    if (!isTableRule(line)) current.rows.push({ lineIndex, cells: splitCells(line) })
  }
  return tables
}

/** 表头行 = 第一行带口径词的格子构成的列名行；找不到就退回表的第一行 */
function headerRowOf(table: Table): TableRow | undefined {
  return (
    table.rows.find((row) => row.cells.some((cell) => FLOW_KEYWORDS.some((word) => cell.includes(word)))) ??
    table.rows[0]
  )
}

/** 判定列数不齐：同一张表内 `|` 分隔数与表头不一致 */
function detectTableColumns(tables: Table[], lines: string[]): MdSuspect[] {
  const found: MdSuspect[] = []
  for (const table of tables) {
    const header = headerRowOf(table)
    if (!header) continue
    const expected = header.cells.length
    const critical = header.cells.some((cell) => FLOW_KEYWORDS.some((word) => cell.includes(word)))
    for (const row of table.rows) {
      if (row === header || row.cells.length === expected) continue
      // 续表里重复打出来的列名行不是错行
      if (row.cells.some((cell) => COLUMN_NOUNS.includes(cell))) continue
      const line = lines[row.lineIndex] ?? ''
      const gap = row.cells.length - expected
      found.push({
        kind: 'table-columns',
        lineIndex: row.lineIndex,
        line,
        hint:
          gap < 0
            ? `表格列数不齐：这行只有 ${row.cells.length} 格，表头有 ${expected} 格，疑似错行丢了一列`
            : `表格列数不齐：这行有 ${row.cells.length} 格，表头只有 ${expected} 格，疑似错行多出一列`,
        severity: critical ? 'high' : 'low',
        match: line.trim(),
      })
    }
  }
  return found
}

/**
 * 逐格看数字：`D/C` 前缀（high）与整数位数异常（low）。
 *
 * `D/C` 前缀只认「整格就是 `D123.45`」这种最典型形态，所以不做列名限定 ——
 * 无论哪一列出现都值得看一眼。位数异常则**必须**落在金额类列下（见
 * `AMOUNT_COLUMN_KEYWORDS`），否则账号卡号会被满表误标。
 */
function detectAmountCells(tables: Table[], lines: string[]): MdSuspect[] {
  const found: MdSuspect[] = []
  for (const table of tables) {
    const header = headerRowOf(table)
    const amountColumns = new Set<number>()
    header?.cells.forEach((cell, i) => {
      if (AMOUNT_COLUMN_KEYWORDS.some((word) => cell.includes(word))) amountColumns.add(i)
    })
    for (const row of table.rows) {
      const line = lines[row.lineIndex] ?? ''
      for (const [columnIndex, cell] of row.cells.entries()) {
        const prefixed = AMOUNT_PREFIX.exec(cell)
        if (prefixed) {
          found.push({
            kind: 'amount-prefix',
            lineIndex: row.lineIndex,
            line,
            hint: `金额前混入借贷标记「${prefixed[1]}」：应为 ${prefixed[2]}，疑为 D（借方）/ C（贷方）标记跑进了数字`,
            severity: 'high',
            match: cell,
          })
          continue
        }
        // 只判金额列下的纯整数格：带小数点的是正常金额，位数不宜套用同一把尺
        if (!amountColumns.has(columnIndex)) continue
        if (!NUMBER_CELL.test(cell) || cell.includes('.')) continue
        const digits = cell.replace(/,/g, '').replace(/^-/, '').length
        if (digits >= MIN_AMOUNT_INT_DIGITS && digits <= MAX_AMOUNT_INT_DIGITS) continue
        found.push({
          kind: 'digit-width',
          lineIndex: row.lineIndex,
          line,
          hint: `数字位数异常：这一格是 ${digits} 位整数，超出 ${MIN_AMOUNT_INT_DIGITS}–${MAX_AMOUNT_INT_DIGITS} 位，疑为被截断或被拼错`,
          severity: 'low',
          match: cell,
        })
      }
    }
  }
  return found
}

const isLongDate = (cell: string): boolean => DATE_LONG.some((re) => re.test(cell))

/**
 * 日期丢位：6 位数字落在表格格子里，且**同一列里还有 8 位日期**。
 *
 * 「8 位同伴」这个前提不能省，而且必须限定在**同一列**：没有它，6 位卡号短号、
 * 流水尾号、科目代号全会被误标。只看同表也不够——一张流水表同时有交易日期列和
 * 卡号列，卡号尾号 123456 会跟 8 位日期住在同一行，按「同表」判就全中；
 * 按「同列」判才准：8 位日期所在的列才是日期列。
 */
function detectDateShort(tables: Table[], lines: string[]): MdSuspect[] {
  const found: MdSuspect[] = []
  for (const table of tables) {
    const width = Math.max(0, ...table.rows.map((row) => row.cells.length))
    for (let columnIndex = 0; columnIndex < width; columnIndex++) {
      const columnOf = (row: TableRow) => row.cells[columnIndex]
      if (!table.rows.some((row) => { const c = columnOf(row); return c !== undefined && isLongDate(c) })) continue
      for (const row of table.rows) {
        const cell = columnOf(row)
        if (cell === undefined || !DATE_SHORT.test(cell)) continue
        found.push({
          kind: 'date-short',
          lineIndex: row.lineIndex,
          line: lines[row.lineIndex] ?? '',
          hint: `日期只有 ${cell.length} 位：同一列的其它日期是 8 位（YYYYMMDD），这一格丢了 ${8 - cell.length} 位`,
          severity: 'high',
          match: cell,
        })
      }
    }
  }
  return found
}

/**
 * 表头残缺 / 表头结构异常：OCR 会把表名切掉一截、或把表名与列名粘成一行。
 *
 * ═══ 为什么不用「长度」当判据 ═══
 * 实测的两个真实表头只差一个首字：「通借记卡主活期账户交易明细表」（14 字，缺「恒」）
 * 与「恒通借记卡主活期账户交易明细表」（15 字，完整）。纯长度阈值切不开这两者，
 * 压得松会把所有正常表头标上，压得紧就一个都抓不到。而表头误报的判定成本很高
 * （律师得去翻原图核对首字）——不像 `D3.00` 那样一眼能判掉。误报一多，律师就
 * 从此不再看任何标记，标记功能等于失效。所以这里只认**结构**上能确证的形态。
 *
 * ═══ 三条形态 ═══
 * 1. 表名粘连列名：`…明细表: 易日期 对方账号 摘要`（冒号后接列名词）—— high
 * 2. 列名独立成行：整行只剩一排列名（>= 3 个列名词），表名整段丢失 —— high
 * 3. 表头与表格列数不匹配：表头行没有 `|` 分隔，下面的表格却有多列 —— low，
 *    措辞保持中性（不说「缺字」），因为完整的短表名同样会落进这条。
 */
function detectCaptionTruncated(tables: Table[]): MdSuspect[] {
  const found: MdSuspect[] = []
  for (const table of tables) {
    const caption = table.caption
    if (!caption || caption.text.length > MAX_CAPTION_CHARS) continue
    const text = caption.text
    const nouns = COLUMN_NOUNS.filter((noun) => text.includes(noun))

    // 形态 1：表名后粘着一串列名（冒号是粘合处）
    const colon = text.search(/[：:]/)
    if (colon >= 0 && COLUMN_NOUNS.some((noun) => text.slice(colon).includes(noun))) {
      found.push({
        kind: 'header-truncated',
        lineIndex: caption.lineIndex,
        line: caption.text,
        hint: '表格标题疑似被截断：表名后直接接了一串列名，中间的表名部分丢了',
        severity: 'high',
        match: text,
      })
      continue
    }

    // 形态 2：整行就是一排列名，表名整段丢失（>= 3 个列名词才算，见 MIN_COLUMN_NOUN_HITS）
    if (nouns.length >= MIN_COLUMN_NOUN_HITS) {
      found.push({
        kind: 'header-truncated',
        lineIndex: caption.lineIndex,
        line: caption.text,
        hint: '表格标题疑似被截断：这一行只剩列名，表名整段缺失',
        severity: 'high',
        match: text,
      })
      continue
    }

    // 形态 3：表头没有列分隔，下方表格却是多列表 —— 表头结构有问题，需要人看一眼。
    // 中性措辞：完整的短表名也会命中这条，不能断言「缺字」。
    const firstRow = table.rows[0]
    if (text.includes('|') || !firstRow || firstRow.cells.length < MIN_TABLE_COLUMNS) continue
    found.push({
      kind: 'header-truncated',
      lineIndex: caption.lineIndex,
      line: caption.text,
      hint: '表头与表格列数不匹配，请确认表头是否完整',
      severity: 'low',
      match: text,
    })
  }
  return found
}

/** 主入口：按 markdown 行序返回全部可疑点 */
export function findSuspects(markdown: string): MdSuspect[] {
  if (!markdown.trim()) return []
  const lines = markdown.split('\n')
  const tables = collectTables(lines)
  return [
    ...detectAmountCells(tables, lines),
    ...detectDateShort(tables, lines),
    ...detectTableColumns(tables, lines),
    ...detectCaptionTruncated(tables),
  ].sort((a, b) => a.lineIndex - b.lineIndex)
}
