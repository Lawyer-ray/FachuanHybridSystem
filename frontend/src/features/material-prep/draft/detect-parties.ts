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
 *   对方当事人      ← 「借款人：」「被告：」「甲方（借款人）：」「被申请人：」
 *
 * 标签优先，再按出现频次投票。这样「催收人：某某某」「经办人：某某某」
 * 这类内部人员就不会被误当成当事人。
 *
 * ═══ 边界 ═══
 * · 只填**空**字段，不覆盖律师手填/改过的内容（要覆盖机填值走「重新识别」，见
 *   `applyDetectedParties` 的 replaceAuto）
 * · 识别不出就不填，不猜 —— 空的输入框比填错的好
 * · 只取当事人姓名/单位名，不碰身份证号、地址（那些走别的字段）
 *
 * ═══ 本模块只做「文本证据」，不做「身份判定」═══
 * 光看标签有一类问题无解：**同一个标签在不同文书里指向相反的两造**（见
 * AMBIGUOUS_OUR_LABELS）。所以本模块产出的 `PartyCandidates` 只是候选，
 * 真正的身份由 `./party-lookup` 拿客户库里已登记的 `is_our_client` 去对账；
 * 客户库查不到时，才退回这里的标签判定。
 */

/**
 * 我方（委托人）强标签。
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
  '抵押权人',
  '债权人',
  '出借人',
]

/**
 * 双向标签：**同一叠纸里，它可能正好指着相反的两造**，所以只能当弱信号。
 *
 * 实测（工伤行政复议卷宗实测）：
 *   ·《行政复议答复书》「申请人：某某山庄饮食有限公司」← 我方委托人
 *   ·《工伤认定申请表》「申请人：苏某某」                              ← 对面职工
 *   ·《认定工伤决定书》「申请人：苏某某」                              ← 对面职工
 * 三处都写「申请人」，按频次投票 2:1 站到职工那边，最终右栏填出
 * 「苏某某、某某山庄饮食有限公司」—— 两造被拼成同一个委托人，
 * 既多了一个人，又把对面写成了我方。
 *
 * 故「申请人」单独立组：**只有在能排除职工一侧时才算我方证据**（见 detectPartyCandidates）。
 */
const AMBIGUOUS_OUR_LABELS = ['申请人']

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

/**
 * 「受伤职工 / 第三人」这类标签：只说明**这个人不是我们要代表的那一方**，
 * 从不直接填进任何一侧。
 *
 * 唯一用途：当「申请人」出现两个以上不同主体时，把同时被这些标签命名过的那一侧
 * 从委托人候选里剔掉 —— 同一个主体不可能既是我方委托人、又是材料里的「受伤害职工」。
 *
 * ⚠️ **只在有竞争时生效**：员工一方的卷宗里「申请人」只有职工一个名字，
 * 这种卷宗是「申请人（职工）+ 被申请人（单位）」的配对，不会误剔。
 */
const SUBJECT_LABELS = ['受伤害职工', '受伤职工', '职工姓名', '员工姓名', '劳动者', '第三人']

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

/** 「谭某某 梁某某」这种一行多人的拆开；标签值里已有顿号的同样拆 */
function splitNames(name: string): string[] {
  return name
    .split(/\s+|、/)
    .map((x) => x.trim())
    .filter(Boolean)
}

/** 多数投票：同一个名字出现次数最多的那组 */
function topNames(hits: Hit[], max = 3): string[] {
  const tally = new Map<string, number>()
  for (const h of hits) {
    for (const n of splitNames(h.name)) {
      tally.set(n, (tally.get(n) ?? 0) + 1)
    }
  }
  return [...tally.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, max)
    .map(([n]) => n)
}

/** 命中里出现过的**单个**主体名（归属判断用：拼起来的名字要拆开比） */
function nameSet(hits: Hit[]): Set<string> {
  const out = new Set<string>()
  for (const h of hits) for (const n of splitNames(h.name)) out.add(n)
  return out
}

function uniqueNames(names: Iterable<string>): string[] {
  return [...new Set(names)]
}

/** 把识别到的多个名字按用户习惯拼起来（中文顿号分隔） */
export function joinPartyNames(names: readonly string[]): string {
  return names.join('、')
}

/** 按标签分组的命中：同一行只走一个标签，但四个分组各扫一遍（「申请人」不会被当成「原告」） */
function collectHits(draft: DraftState): { strong: Hit[]; ambiguous: Hit[]; their: Hit[]; subject: Hit[] } {
  const buckets = { strong: [] as Hit[], ambiguous: [] as Hit[], their: [] as Hit[], subject: [] as Hit[] }
  for (const seg of draft.segs) {
    const text = seg.md ?? ''
    if (!text) continue
    buckets.strong.push(...scanLabeled(text, OUR_LABELS, NOT_A_PARTY))
    buckets.ambiguous.push(...scanLabeled(text, AMBIGUOUS_OUR_LABELS, NOT_A_PARTY))
    buckets.their.push(...scanLabeled(text, THEIR_LABELS, NOT_A_PARTY))
    buckets.subject.push(...scanLabeled(text, SUBJECT_LABELS, NOT_A_PARTY))
  }
  return buckets
}

export interface PartyCandidates {
  /** 委托人候选（票数降序）：只有标签支持我方时才在这里 */
  ours: string[]
  /** 对方当事人候选（票数降序） */
  theirs: string[]
  /**
   * 正文里出现过的**全部**当事人候选（我方 → 对方 → 职工/第三人，去重、保持顺序）。
   * 交给 `./party-lookup` 逐名去客户库对账：命中客户库的按 `is_our_client` 归类，
   * 查不到才退回 ours/theirs 的标签判定。
   */
  names: string[]
}

/** 扫全部段落的正文，产出两侧候选（纯文本证据，不做身份判定） */
export function detectPartyCandidates(draft: DraftState): PartyCandidates {
  const b = collectHits(draft)
  const theirNames = nameSet(b.their)
  const subjectNames = nameSet(b.subject)
  const strongNames = nameSet(b.strong)
  // 「申请人」出现两个以上不同主体 = 这叠纸里有两个申请人（复议申请人 + 工伤认定申请人）。
  // 单靠标签分不出哪一边是我们，这时被「职工/第三人」命名过的那一侧必定是对面。
  const ambiguousCompetes = nameSet(b.ambiguous).size > 1

  const ours = topNames(
    [...b.strong, ...b.ambiguous].filter((h) => {
      const names = splitNames(h.name)
      // 同一人不可能在两造：以对方名单优先（借款人/被告指向性更强）
      if (names.some((n) => theirNames.has(n))) return false
      if (!ambiguousCompetes) return true
      // 只靠「申请人」进来的候选，若同时被职工/第三人命名过，就是被代表的那一方。
      // 强标签（原告/委托人/贷款人…）命中过的不受这条影响。
      return !names.some((n) => subjectNames.has(n) && !strongNames.has(n))
    }),
  ).filter((n) => !theirNames.has(n))

  const theirs = topNames(b.their).filter((n) => !ours.includes(n))
  return {
    ours,
    theirs,
    names: uniqueNames([...ours, ...theirs, ...subjectNames, ...nameSet(b.ambiguous), ...strongNames]),
  }
}

export interface DetectedParties {
  /** 委托人（我方）：银行 / 原告 / 贷款人 */
  our: string
  /** 对方当事人：借款人 / 被告 */
  their: string
}

/** 只要标签判定的结果（客户库对账的兜底，也是单测与旧调用方的入口） */
export function detectParties(draft: DraftState): DetectedParties {
  const { ours, theirs } = detectPartyCandidates(draft)
  return { our: joinPartyNames(ours), their: joinPartyNames(theirs) }
}

/**
 * 把识别结果回填到 infos。
 *
 * 默认 **只填空字段**，不动律师已填/已改的内容。
 * `replaceAuto` 供「重新识别当事人」按钮用：把**机填值**（`src === '自动识别'`）
 * 也一并接管 —— 否则第一次识别错了就永远改不掉（只填空的规则会把它当成律师输入）。
 * 律师手填 / 从客户库选过标签的字段（src 为空或别的来源）依旧不动。
 *
 * 返回是否存在改动（决定要不要触发保存）。
 */
export function applyDetectedParties(
  infos: DraftState['infos'],
  detected: DetectedParties,
  opts: { replaceAuto?: boolean } = {},
): { infos: DraftState['infos']; changed: boolean } {
  let changed = false
  const next = infos.map((f) => {
    const writable = !f.v?.trim() || (opts.replaceAuto === true && f.src === '自动识别')
    if (!writable) return f // 律师填过 / 改过的，跳过
    const v = f.k === '委托人' ? detected.our : f.k === '对方当事人' ? detected.their : ''
    if (f.k !== '委托人' && f.k !== '对方当事人') return f
    // 重新识别但这一侧没识别出来 → 清掉上次的机填值（错值比空值更费律师）
    const nextV = v || (opts.replaceAuto === true ? '' : f.v)
    if (nextV === f.v) return f
    changed = true
    return nextV ? { ...f, v: nextV, src: '自动识别' } : { ...f, v: '', src: '' }
  })
  return { infos: changed ? next : infos, changed }
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
