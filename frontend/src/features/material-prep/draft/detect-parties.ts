import type { DraftState } from '../types'

/**
 * 从分段正文里**自动识别当事人**，回填右栏「委托人 / 对方当事人」。
 *
 * ═══ 为什么需要它 ═══
 * 分段完成后，12 份材料的 OCR 正文已经躺在草稿里了 —— 借款人是谁、
 * 银行是哪家、身份证号多少，全都在里面。但右栏那两个输入框还是空的，
 * 律师得自己翻材料手打一遍。这正是机器该干的活。
 *
 * ═══ 识别策略（按可信度从高到低）═══
 * 不是简单正则扫一遍就完事。同一叠纸里当事人会被反复提到，但
 * 「甲方的名字」和「客户经理的名字」在正文里长得一样，必须靠**字段标签**定位：
 *
 *   委托人（我方）  ← 「贷款人：」「报送单位：」「原告：」「委托人：」「甲方（贷款人）」
 *   对方当事人      ← 「借款人：」「被告：」「甲方（借款人）：」「申请人：」
 *
 * 标签优先，再按出现频次投票。这样「催收人：某某某」「经办人：某某某」
 * 这类内部人员就不会被误当成当事人。
 *
 * ═══ 边界 ═══
 * · 只填**空**字段，不覆盖律师手填/改过的内容
 * · 识别不出就不填，不猜 —— 空的输入框比填错的好
 * · 只取当事人姓名/单位名，不碰身份证号、地址（那些走别的字段）
 */

/**
 * 我方（委托人）标签。
 *
 * ⚠️ 只收**放款方/权利方**的标签。早先把「抵押人」「义务人」也放进来，
 * 结果「抵押人（丙方）：谭某某」把借款人也算成了委托人 ——
 * 抵押人就是借款人自己（以自己房产抵押），他永远在对面。
 */
const OUR_LABELS = [
  '贷款人（乙方）',
  '贷款人',
  '报送单位',
  '委托单位',
  '委托人',
  '原告',
  '申请人',
  '抵押权人',
  '债权人',
  '出借人',
]

/**
 * 对方（借款人/被告）标签。
 *
 * 「抵押人」「义务人」「债务人」都归这边：本案里抵押人就是借款人（自有房产抵押），
 * 不是第三方担保人。若将来出现真正的第三方抵押人，应另起字段而非混进来。
 */
const THEIR_LABELS = [
  '借款人（甲方）',
  '借款人',
  '被告',
  '被上诉人',
  '被申请人',
  '抵押人（丙方）',
  '抵押人',
  '义务人',
  '债务人',
]

/** 明确不是当事人的角色（内部人员、第三方机构），命中就跳过 */
const NOT_A_PARTY = [
  '经办人',
  '复核人',
  '催收人',
  '调查人',
  '审查人',
  '审批人',
  '面谈人',
  '见证人',
  '估价师',
  '审判员',
  '书记员',
  '公证员',
  '收件人',
  '确认人',
  '联系人',
  '代理人',
  '负责人',
  '法定代表人',
  '权属人',
]

interface Hit {
  name: string
  label: string
  count: number
}

/**
 * 从一段文本里抽「标签：值」。
 *
 * 支持的分隔：中英文冒号、全角空格。值只取到行尾或下一个分隔符，
 * 并截掉括号里的补充说明（`谭某某（身份证 …）` → `谭某某`）。
 */
function scanLabeled(text: string, labels: string[], exclude: string[]): Hit[] {
  const hits: Hit[] = []
  // ⚠️ 标签按长度降序：`借款人（甲方）` 必须排在 `借款人` 前面，
  //    否则裸标签先命中，带括号的更长标签永远轮不到，
  //    「借款人（甲方）：谭某某」就会被 `借款人` 匹配到「（甲方）：…」这种脏值。
  const ordered = [...labels].sort((a, b) => b.length - a.length)
  // 按行扫：真实材料都是「标签：值」一行一条
  for (const rawLine of text.split(/\n/)) {
    const line = rawLine.trim()
    if (!line || line.length > 120) continue

    for (const label of ordered) {
      // 标签后面必须紧跟冒号（允许中间有空格），避免「借款人基本情况」误命中
      const re = new RegExp(`^${escapeRe(label)}\\s*[:：]\\s*(.+)$`)
      const m = re.exec(line)
      if (!m) continue

      // m[1] 在 noUncheckedIndexedAccess 下是 string | undefined，但正则已有 `(.+)` 捕获组，
      // 匹配成功时必然存在；`!` 把这个事实告诉类型系统。
      const value = cleanName(m[1]!)
      if (!value) continue
      // 被排除的角色（内部人员）不作为当事人
      if (exclude.some((e) => value.includes(e)) || exclude.some((e) => label.includes(e))) continue
      // 人名/单位名长度兜底，避免把整句话当名字
      if (value.length > 40) continue
      // 残留的字段名/证件号（清完之后仍像字段的，直接丢）
      if (looksLikeFieldOrCode(value)) continue

      hits.push({ name: value, label, count: 1 })
      break
    }
  }
  return hits
}

/**
 * 只保留姓名/单位名。
 *
 * 实测踩过两次坑，都在这一个函数里：
 *  ① 括号说明没清干净：`谭某某（身份证 110101199305110011）` →
 *     全角括号里的内容被当成了名字的一部分，最终输出「身份证号：…」。
 *  ② 一行里带多个字段：`借款人：谭某某\u3000\u3000身份证号：1101...`（全角空格分隔）
 *     只按逗号切不够，得先把后续的「XX：」段砍掉。
 */
function cleanName(raw: string): string {
  let v = raw
    // ① 括号里的补充说明（全角/半角都清，可能嵌套）
    .replace(/[（(][^（）()]*[）)]/g, '')
  // ② 砍掉后面的「字段名：值」—— 一行里常有「借款人：谭某某\u3000身份证号：1101…」
  v = v.replace(/\s+[\u4e00-\u9fa5A-Za-z]{2,8}\s*[:：].*$/, '')
  v = v
    .split(/[，,；;]/)[0]!
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[。、：:；;.\s]+$/, '')
    .trim()
  // ③ 职务尾巴：「陈某某 行长」→「陈某某」
  v = v.replace(/\s+(行长|经理|主任|律师|法官|先生|女士|同志)$/, '')
  return v
}

/** 明显不是「名字」的残留（字段名、证件号、编号），命中就丢弃 */
function looksLikeFieldOrCode(v: string): boolean {
  if (/[:：]/.test(v)) return true // 还带冒号说明没切干净
  if (/\d{6,}/.test(v)) return true // 长数字串（证件号/编号）
  if (/^(身份证|合同|借据|报告|凭证|编号|账号|电话|地址|金额)/.test(v)) return true
  if (v.length < 2) return true
  return false
}

/** 多数投票：同一个名字出现次数最多的那组 */
function topNames(hits: Hit[], max = 3): string[] {
  const tally = new Map<string, number>()
  for (const h of hits) {
    // 「谭某某 梁某某」这种一行多人的，拆开分别计数
    for (const n of h.name.split(/\s+|、/).map((x) => x.trim()).filter(Boolean)) {
      tally.set(n, (tally.get(n) ?? 0) + 1)
    }
  }
  return [...tally.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, max)
    .map(([n]) => n)
}

/** 把识别到的多个名字按用户习惯拼起来（中文顿号分隔） */
function joinNames(names: string[]): string {
  return names.join('、')
}

export interface DetectedParties {
  /** 委托人（我方）：银行 / 原告 / 贷款人 */
  our: string
  /** 对方当事人：借款人 / 被告 */
  their: string
}

/**
 * 扫描整个草稿的所有分段正文，识别两侧当事人。
 *
 * 为什么扫**全部**分段而不是只看某一份：当事人的完整信息散在多份材料里 ——
 * 不良贷款监控报告有「借款人/报送单位」，贷款申请有「申请人/配偶」，
 * 送达地址确认书有「收件人」。单看一份会漏。
 */
export function detectParties(draft: DraftState): DetectedParties {
  const our: Hit[] = []
  const their: Hit[] = []

  for (const seg of draft.segs) {
    const text = seg.md ?? ''
    if (!text) continue
    our.push(...scanLabeled(text, OUR_LABELS, NOT_A_PARTY))
    their.push(...scanLabeled(text, THEIR_LABELS, NOT_A_PARTY))
  }

  const theirNames = topNames(their)
  // 我方名单里剔掉已在对方名单出现的名字。
  // 为什么需要：一份材料里同一个人可能被两个标签提到
  // （「借款人：谭某某」+「抵押人：谭某某」），而不同材料的标签归属
  // 偶尔会串（早期实测「抵押人」被算进我方）。同一个人不可能同时在两造，
  // 所以以**对方名单优先**为准 —— 借款人/被告的标签指向性更强。
  const ourNames = topNames(our).filter((n) => !theirNames.includes(n))

  return {
    our: joinNames(ourNames),
    their: joinNames(theirNames),
  }
}

/**
 * 把识别结果回填到 infos。**只填空字段**，不动律师已填/已改的内容。
 *
 * 返回是否存在改动（决定要不要触发保存）。
 */
export function applyDetectedParties(
  infos: DraftState['infos'],
  detected: DetectedParties,
): { infos: DraftState['infos']; changed: boolean } {
  let changed = false
  const next = infos.map((f) => {
    if (f.v?.trim()) return f // 已有值，跳过
    if (f.k === '委托人' && detected.our) {
      changed = true
      return { ...f, v: detected.our, src: '自动识别' }
    }
    if (f.k === '对方当事人' && detected.their) {
      changed = true
      return { ...f, v: detected.their, src: '自动识别' }
    }
    return f
  })
  return { infos: changed ? next : infos, changed }
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
