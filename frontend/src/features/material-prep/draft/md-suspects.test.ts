import { findSuspects } from './md-suspects'

/**
 * Markdown 可疑点检测单测（node 环境，纯函数、纯正则）。
 *
 * 每条判据都配「正例 + 反例」，且**反例一律是「看似可疑但其实合法」的真实形态**
 * （22 位账号、6 位短号、无金额列的两列表、正文里的短表名……）。
 * 这不是为了凑数：这些反例就是将来有人想把判据「顺手放宽」时会被踩到的地雷，
 * 留着它们才能挡住误改宽。
 *
 * 数据全部虚构：账号、卡号、名称都是拼的示例值。
 */

/** 一张典型流水表：列名行 + 分隔行 + 若干数据行 */
function table(rows: string[]): string {
  return ['| 交易日期 | 对方账号 | 摘要 | 发生额 | 当前余额 | 交易卡号 |', '| --- | --- | --- | --- | --- | --- |', ...rows].join('\n')
}

const kindsOf = (markdown: string) => findSuspects(markdown).map((s) => s.kind)

describe('findSuspects：整体契约', () => {
  it('空输入与纯正文返回空数组（无表格就没有任何判据可跑）', () => {
    expect(findSuspects('')).toEqual([])
    expect(findSuspects('   \n\n  ')).toEqual([])
    expect(findSuspects('这是一段普通正文，没有表格，也没有金额。')).toEqual([])
  })

  it('结果按 markdown 行序返回，且带原始行内容供 UI 高亮', () => {
    const md = ['| 摘要 | 发生额 |', '| --- | --- |', '| 代付款 | D3.00 |', '| 代付款 | C12.00 |'].join('\n')
    const got = findSuspects(md)
    expect(got.map((s) => s.lineIndex)).toEqual([2, 3])
    expect(got[0]).toMatchObject({ lineIndex: 2, line: '| 代付款 | D3.00 |', match: 'D3.00' })
    expect(got[1]).toMatchObject({ lineIndex: 3, match: 'C12.00' })
  })
})

describe('amount-prefix：金额前混入 D/C 借贷标记', () => {
  it('正例：整格就是 D3.00 / C3159.44 时命中（high）', () => {
    const md = table([
      '| 20170301 | 3108013602199900800101 | 联动收费手续费 | D3.00 | 18367.70 | 6223221027175157 |',
      '| 20170302 | 3108013602199900800101 | 代付款 | C3159.44 | 18159.05 | 6223221027175157 |',
    ])
    const got = findSuspects(md).filter((s) => s.kind === 'amount-prefix')
    expect(got.map((s) => s.match)).toEqual(['D3.00', 'C3159.44'])
    expect(got.every((s) => s.severity === 'high')).toBe(true)
    expect(got[0]!.hint).toContain('D')
  })

  it('正例：带千分位的 D1,234.56 也命中', () => {
    expect(kindsOf(table(['| 20170301 | 3108 | 代付款 | D1,234.56 | 18159.05 | 622322 |']))).toContain('amount-prefix')
  })

  it('反例：科目代号 C1001 / D202 这类纯字母+数字编码不命中（没有 .00 小数）', () => {
    const md = table(['| 20170301 | 3108 | 代付款 | C1001 | D202 | 622322 |'])
    expect(kindsOf(md)).not.toContain('amount-prefix')
  })

  it('反例：摘要里合法出现 D / C（如「DVD 支付」「C 类结算」）不命中', () => {
    const md = table(['| 20170301 | 3108 | DVD 支付 C 类结算 | 3159.44 | 18159.05 | 622322 |'])
    expect(kindsOf(md)).not.toContain('amount-prefix')
  })

  it('反例：正常金额 3159.44 与「D」隔着空格（`D 3.00` 不算粘连）不命中', () => {
    const md = table(['| 20170301 | 3108 | 代付款 | D 3.00 | 18159.05 | 622322 |'])
    expect(kindsOf(md)).not.toContain('amount-prefix')
  })
})

describe('date-short：6 位日期丢位', () => {
  it('正例：同表有 8 位日期时，6 位日期格命中（high）', () => {
    const md = table([
      '| 20170301 | 3108013602199900800101 | 代付款 | 3.00 | 18367.70 | 6223221027175157 |',
      '| 170201 | 3108013602199900800101 | 代付款 | 3.00 | 18159.05 | 6223221027175157 |',
    ])
    const got = findSuspects(md).filter((s) => s.kind === 'date-short')
    expect(got.map((s) => s.match)).toEqual(['170201'])
    expect(got[0]!.severity).toBe('high')
    expect(got[0]!.lineIndex).toBe(3)
  })

  it('正例：8 位日期带分隔符（2017-03-01）时，6 位同伴也命中', () => {
    const md = table([
      '| 2017-03-01 | 3108 | 代付款 | 3.00 | 18367.70 | 622322 |',
      '| 170201 | 3108 | 代付款 | 3.00 | 18159.05 | 622322 |',
    ])
    expect(kindsOf(md)).toContain('date-short')
  })

  it('反例：全表只有 6 位数字（账号短号），没有 8 位日期作伴时不报', () => {
    const md = table(['| 310801 | 310802 | 代付款 | 3.00 | 18367.70 | 622322 |'])
    expect(kindsOf(md)).not.toContain('date-short')
  })

  it('反例：8 位日期旁的 6 位卡号尾号不报（该格不是日期列）', () => {
    const md = ['| 交易日期 | 交易卡号 |', '| --- | --- |', '| 20170301 | 123456 |'].join('\n')
    expect(kindsOf(md)).not.toContain('date-short')
  })
})

describe('table-columns：表格错行（列数不齐）', () => {
  it('正例：某行少一列时命中，hint 说清少了多少（high）', () => {
    const md = table([
      '| 20170301 | 3108 | 代付款 | 3.00 | 18367.70 | 622322 |',
      '| 20170302 | 3108 | 代付款 | 3.00 | 18159.05 |',
    ])
    const got = findSuspects(md).filter((s) => s.kind === 'table-columns')
    expect(got).toHaveLength(1)
    expect(got[0]!.lineIndex).toBe(3)
    expect(got[0]!.severity).toBe('high')
    expect(got[0]!.hint).toContain('5 格')
    expect(got[0]!.hint).toContain('6 格')
  })

  it('正例：某行多一列时命中（含金额/日期的表按 high）', () => {
    const md = table(['| 20170301 | 3108 | 代付款 | 3.00 | 18367.70 | 622322 | 多余 |'])
    const got = findSuspects(md).filter((s) => s.kind === 'table-columns')
    expect(got).toHaveLength(1)
    expect(got[0]!.hint).toContain('多出一列')
  })

  it('反例：跨页续表重复打了一遍列名行，不算错行', () => {
    const md = [
      '| 交易日期 | 对方账号 | 摘要 | 发生额 | 当前余额 | 交易卡号 |',
      '| --- | --- | --- | --- | --- | --- |',
      '| 20170301 | 3108 | 代付款 | 3.00 | 18367.70 | 622322 |',
      '| 交易日期 | 对方账号 | 摘要 | 发生额 | 当前余额 | 交易卡号 |',
      '| 20170302 | 3108 | 代付款 | 3.00 | 18159.05 | 622322 |',
    ].join('\n')
    expect(kindsOf(md)).not.toContain('table-columns')
  })

  it('反例：两张列数不同的表前后相邻（各自有列名行），互不干扰', () => {
    const md = ['| 交易日期 | 对方账号 |', '| --- | --- |', '| 20170301 | 3108 |', '', '| 项目 | 金额 | 备注 |', '| --- | --- | --- |', '| 本金 | 3.00 | 无 |'].join('\n')
    expect(kindsOf(md)).not.toContain('table-columns')
  })
})

describe('header-truncated：表头残缺 / 表头结构异常', () => {
  it('正例：表名与列名粘连成一行（实测形态）→ 命中且为 high', () => {
    const md = ['通借记卡主活期账户交易明细表: 交易日期 对方账号 摘要 发生额', ...table([]).split('\n')].join('\n')
    const got = findSuspects(md).filter((s) => s.kind === 'header-truncated')
    expect(got).toHaveLength(1)
    expect(got[0]!.lineIndex).toBe(0)
    expect(got[0]!.severity).toBe('high')
    expect(got[0]!.hint).toContain('列名')
  })

  it('正例：整行只剩一排列名（表名整段丢失）→ 命中且为 high', () => {
    const md = ['易日期 对方账号 摘要 发生额', ...table([]).split('\n')].join('\n')
    const got = findSuspects(md).filter((s) => s.kind === 'header-truncated')
    expect(got).toHaveLength(1)
    expect(got[0]!.severity).toBe('high')
    expect(got[0]!.hint).toContain('表名整段缺失')
  })

  it('正例：表头无列分隔、下方却是多列表 → 命中但只报 low，且措辞不预设「缺字」', () => {
    const md = ['通借记卡主活期账户交易明细表', ...table([]).split('\n')].join('\n')
    const got = findSuspects(md).filter((s) => s.kind === 'header-truncated')
    expect(got).toHaveLength(1)
    expect(got[0]!.severity).toBe('low')
    // 完整的短表名也会落进这条，所以不能断言「缺字」，只能请人确认
    expect(got[0]!.hint).toBe('表头与表格列数不匹配，请确认表头是否完整')
  })

  it('反例：正文里只有 2 个列名词（「日期 金额」）不报', () => {
    const md = ['本表列出日期 金额两个口径', ...table([]).split('\n')].join('\n')
    const got = findSuspects(md).filter((s) => s.kind === 'header-truncated')
    // 不是列名残句（够不上 3 个列名词），但作为「无分隔表头」仍会被 low 兜住；
    // 这里断言的是它没有被误判成 high
    expect(got.every((s) => s.severity === 'low')).toBe(true)
  })

  it('反例：两列小表的短表名不报（列数 < 3，够不上「结构异常」）', () => {
    const md = ['项目 金额', '| 项目 | 金额 |', '| --- | --- |', '| 本金 | 3.00 |'].join('\n')
    expect(kindsOf(md)).not.toContain('header-truncated')
  })
})

describe('digit-width：数字位数异常', () => {
  it('正例：金额列出现 17 位整数时命中（low）', () => {
    const md = table(['| 20170301 | 3108 | 代付款 | 99999999999999999 | 18159.05 | 622322 |'])
    const got = findSuspects(md).filter((s) => s.kind === 'digit-width')
    expect(got.map((s) => s.match)).toEqual(['99999999999999999'])
    expect(got[0]!.severity).toBe('low')
    expect(got[0]!.lineIndex).toBe(2)
  })

  it('正例：13 位整数（刚超上限）与 17 位同样命中', () => {
    const md = table(['| 20170301 | 3108 | 代付款 | 1234567890123 | 18159.05 | 622322 |'])
    expect(kindsOf(md)).toContain('digit-width')
  })

  it('反例：账号列 22 位、卡号列 16 位不报（位数尺只量金额类列）', () => {
    const md = table(['| 20170301 | 3108013602199900800101 | 代付款 | 3.00 | 18159.05 | 6223221027175157 |'])
    expect(kindsOf(md)).not.toContain('digit-width')
  })

  it('反例：带小数点的正常金额（18367.70）与带千分位的金额不报', () => {
    const md = table(['| 20170301 | 3108 | 代付款 | 1,234.56 | 18367.70 | 622322 |'])
    expect(kindsOf(md)).not.toContain('digit-width')
  })
})
