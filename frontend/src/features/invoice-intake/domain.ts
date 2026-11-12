import { formatAmount, MATCH_KIND_STYLES } from './constants'
import type { InvoiceIntake, RedGroup } from './types'

/**
 * 发票待认领的纯领域逻辑（无 React、无 IO），供组件与单测共用。
 */

/** 结论行里案由片段的截断长度：侧栏窄，超过这个长度必然被截掉 */
const REASON_MAX = 30

/**
 * 全部候选里最高等级的匹配信号。
 *
 * 候选已按分数排序，但仍显式挑最高档：`party_name` 的分数可能高于
 * `case_text`（同一个购买方名字出现两次时），而「凭什么是这么想的」应由
 * 信号等级回答，不是分数。
 */
export function topKind(intake: InvoiceIntake) {
  // 防御性取数：后端 schema 若漏字段，这里崩会让整张卡被 ErrorBoundary 换掉
  const kinds = (intake.candidates ?? []).map((c) => c.kind)
  if (kinds.includes('project_code')) return 'project_code' as const
  if (kinds.includes('case_text')) return 'case_text' as const
  if (kinds.includes('party_name')) return 'party_name' as const
  return null
}

/**
 * 卡片结论：一句话说清「系统认为这张票该绑哪个项目」。
 *
 * 有建议 → `确定性匹配：合同名`；没有 → 明说需要人工选择（不给假的确定感）。
 *
 * **不带 ✓ 字符**：调用方已用 Check 图标表达"匹配成功"，文本里再来一个
 * 就成了「✓ ✓」（实测出现过），图标与文案各管一件事。
 */
export function invoiceHeadline(intake: InvoiceIntake): string {
  if (intake.suggested_contract_id == null) return '无可匹配的在办项目，需人工选择'
  const kind = topKind(intake)
  const label = kind ? MATCH_KIND_STYLES[kind].label : '系统建议'
  return `${label}：${intake.suggested_contract_name ?? '未命名项目'}`
}

/**
 * 从备注栏原文里提取案由片段。
 *
 * 备注栏的真实形态是 `2025GZM0001-张某与某公司合同纠纷`：项目号在前、, // privacy-allow 虚构样例，非真实项目号
 * 案由在后用 `-` 连接。剥掉项目号后剩下的才是人一眼能读的案由文字。
 * 超过 {@link REASON_MAX} 字截断加省略号（侧栏一行放不下）。
 */
function reasonExcerpt(intake: InvoiceIntake): string {
  const code = intake.project_code.trim()
  let text = intake.remark.trim()
  if (code && text.startsWith(code)) {
    text = text.slice(code.length).replace(/^[\s\-—_:：]+/, '')
  }
  return text.length > REASON_MAX ? `${text.slice(0, REASON_MAX)}…` : text
}

/** 卡片第二行：`购买方 · 案由片段`（两者任一为空时不留多余分隔符） */
export function invoiceSubtitle(intake: InvoiceIntake): string {
  const buyer = intake.buyer_name.trim()
  const reason = reasonExcerpt(intake)
  return [buyer, reason].filter((part) => part !== '').join(' · ')
}

/**
 * 是否有可以「一键采纳」的系统建议。
 *
 * 后端对没有合格候选的发票不会预选建议（`suggested_contract_id` 为 null），
 * 这里只认这一个判据——发票的候选全部等于 `suggested_contract`，
 * 不存在款项那边「候选是 amount_only 但建议非空」的分裂态。
 */
export function hasUsableSuggestion(intake: InvoiceIntake): boolean {
  return intake.suggested_contract_id != null
}

/**
 * 能不能直接点「确认绑定」：待确认状态 + 有系统建议 + **不是红票**。
 *
 * 红票那一道闸是这次改动的核心安全点（D5）：红票要冲销原票、还要决定是否重开，
 * 走「一键采纳系统建议」只会绑成一个普通蓝票，把账做反。红票有自己的整组入口
 * （{@link canConfirmRedReenact} / RedReenactCard）。
 */
export function canConfirm(intake: InvoiceIntake): boolean {
  return intake.status === 'pending' && hasUsableSuggestion(intake) && !isRed(intake)
}

/** 金额展示（含币种）；识别失败没有金额时给占位而不是 `¥` */
export function amountText(intake: InvoiceIntake): string {
  // 红票的「没金额」和普通票的「没金额」是两件事：前者会让冲红少一笔负数、账直接错，
  // 必须说清是红票没识别出来，否则同一句「金额未识别」会被当成小问题扫过去
  if (intake.total_amount == null || intake.total_amount === '') {
    return isRed(intake) ? '红票金额未识别' : '金额未识别'
  }
  return formatAmount(intake.total_amount)
}

/**
 * 是否红字发票。
 *
 * 判据**只看票面事实**，不看后端算好的 `is_red`：后端判据是
 * `bool(red_against_number) or total_amount < 0`（契约 §模型），前端照抄一遍
 * 是为了在 `is_red` 缺失（旧接口 / 字段漏下发）时仍然不会把红票当蓝票确认。
 * 两个 dim 都有才认：只看负数会把「退款票」误判成红票吗？不会——退款票本身就是
 * 负数票，按票面事实它同样不能走普通确认。
 */
export function isRed(intake: InvoiceIntake): boolean {
  if (intake.red_against_number) return true
  return isNegativeAmount(intake.total_amount)
}

/** 金额是否为负（字符串来自后端 DecimalField，转数失败一律不算负） */
function isNegativeAmount(amount: string | null): boolean {
  if (amount == null || amount === '') return false
  const value = Number(amount)
  return Number.isFinite(value) && value < 0
}

/** 票号尾部片段：整串 20 位号码在侧栏放不下，取尾 6 位已足够人对上 */
function shortNumber(invoiceNumber: string): string {
  const text = invoiceNumber.trim()
  if (text === '') return '号码未识别'
  return text.length > 6 ? `…${text.slice(-6)}` : text
}

/**
 * 红票的结论行：不说「建议绑哪个项目」，说「冲销哪张票」。
 *
 * 原票在库 → `冲销 …368336（¥40,000.00）`；不在库 → 明说需人工处理，
 * 而不是留一句没有信息的占位。
 */
export function redHeadline(intake: InvoiceIntake): string {
  const number = shortNumber(intake.red_against_number)
  const original = intake.offset_invoice
  if (original == null) return `冲销 ${number}（原票不在系统里）`
  const amount = original.total_amount
  const text = amount == null || amount === '' ? '金额未识别' : formatAmount(amount)
  return `冲销 ${number}（${text}）`
}

/**
 * 能不能一键「冲红并确认重开」（整组一次请求）。
 *
 * 四个条件缺一不可：
 * 1. 有红票（没有红票就没有可冲的东西）；
 * 2. 原票在库（`original !== null`）——注意**不能看红票自己的 `offset_invoice`**，
 *    它可能为空而组里已给出原票，反之亦然；组结构的 `original` 是唯一权威；
 * 3. 红票金额已识别——金额未知时冲红会让 `Sum` 少一笔负数，账直接错；
 * 4. 组内挑到了金额非空的新蓝票（没有新票就只是「仅冲红」）。
 */
export function canConfirmRedReenact(group: RedGroup | null): boolean {
  if (group == null) return false
  if (group.original == null) return false
  if (group.red.total_amount == null || group.red.total_amount === '') return false
  const reissue = group.reissue
  if (reissue == null) return false
  return reissue.total_amount != null && reissue.total_amount !== ''
}

/** 一组冲红重开（成员已按「红 → 新」顺序排好） */
export interface IntakeGroup {
  groupKey: string
  items: InvoiceIntake[]
}

/**
 * 把待认领列表拆成「红票组」与「单行」。
 *
 * 同一组的红票和重开的新蓝票是**两条独立 intake**：不聚合的话一次冲红重开会让
 * 待办从 1 条变 2 条，还得让人自己看出这是一件事。组内顺序固定为红票在前、
 * 新票在后（后端保证，这里显式排一遍），卡片据此渲染三段。
 */
export function splitByRedGroup(list: InvoiceIntake[]): {
  groups: IntakeGroup[]
  standalones: InvoiceIntake[]
} {
  const groups: IntakeGroup[] = []
  const byKey = new Map<string, IntakeGroup>()
  const standalones: InvoiceIntake[] = []

  for (const intake of list) {
    const key = intake.reatch_group?.group_key
    if (!key) {
      standalones.push(intake)
      continue
    }
    const existing = byKey.get(key)
    if (existing) {
      existing.items.push(intake)
      continue
    }
    const group: IntakeGroup = { groupKey: key, items: [intake] }
    byKey.set(key, group)
    groups.push(group)
  }

  for (const group of groups) {
    // 红票在前、新票在后；同角色多张时保持原顺序（sort 在 V8 上是稳定的）
    group.items.sort((a, b) => redRank(a) - redRank(b))
  }

  return { groups, standalones }
}

/** 组内排序权重：红票 0、其余 1 */
function redRank(intake: InvoiceIntake): number {
  return isRed(intake) ? 0 : 1
}

/**
 * 角标数：**待办的有几件事**，不是几条 intake。
 *
 * 一组冲红重开在用户眼里是一件事（点一次主按钮就处理完了），按原始条数会从
 * 1 跳到 2，看起来像「越处理越多」。
 */
export function pendingBadgeCount(groups: IntakeGroup[], standalones: InvoiceIntake[]): number {
  return standalones.length + groups.length
}
