/**
 * 演示数据 · C. 要素式转换
 *
 * 这一页的演示要回答律师三个问题：我该用哪个文书类型、转换到底改了哪几处、
 * 转完的东西长什么样。下面的常量分别对应这三问：
 *   文书类型库 → 选哪个（并给出本月用量，说明哪个是主力）
 *   字段映射   → 改了哪几处（含必填与示例值，让人能对照自己的起诉状）
 *   前后对比   → 长什么样（左传统、右要素式，同一段事实两种写法）
 * 真实功能上线时整个文件删除即可。
 */

export interface ConvertLogRow {
  id: number
  originalName: string
  typeName: string
  at: string
  /** 原文件页数 */
  pages: number
  /** 转换耗时（毫秒） */
  ms: number
  /** 结果：成功 / 失败（原文件格式不支持或后端开关未开） */
  ok: boolean
}

export const DEMO_CONVERT_LOG: ConvertLogRow[] = [
  { id: 15, originalName: '起诉状_谭某某_定稿.docx', typeName: '金融借款起诉状', at: '2026-11-03 10:12', pages: 4, ms: 1840, ok: true },
  { id: 14, originalName: '起诉状_吴某某_定稿.docx', typeName: '金融借款起诉状', at: '2026-11-03 10:08', pages: 4, ms: 2106, ok: true },
  { id: 13, originalName: '起诉状_陈某某.docx', typeName: '信用卡纠纷起诉状', at: '2026-11-03 09:51', pages: 3, ms: 1622, ok: true },
  { id: 12, originalName: '起诉状_某某公司（扫描件）.pdf', typeName: '借款合同纠纷起诉状', at: '2026-11-02 17:26', pages: 6, ms: 0, ok: false },
  { id: 11, originalName: '起诉状_林某某.docx', typeName: '借款合同纠纷起诉状', at: '2026-11-02 16:47', pages: 5, ms: 2380, ok: true },
  { id: 10, originalName: '上诉状_某某贸易公司.docx', typeName: '民事上诉状', at: '2026-11-02 15:03', pages: 7, ms: 2740, ok: true },
  { id: 9, originalName: '起诉状_保证合同_汇总.docx', typeName: '保证合同纠纷起诉状', at: '2026-11-01 16:20', pages: 9, ms: 3215, ok: true },
  { id: 8, originalName: '起诉状_抵押合同_汇总.docx', typeName: '抵押合同纠纷起诉状', at: '2026-11-01 15:08', pages: 8, ms: 2960, ok: true },
  { id: 7, originalName: '起诉状_融资租赁_首期.docx', typeName: '融资租赁合同纠纷起诉状', at: '2026-11-01 11:34', pages: 6, ms: 2210, ok: true },
  { id: 6, originalName: '起诉状_买卖合同_某某公司.docx', typeName: '买卖合同纠纷起诉状', at: '2026-10-31 15:52', pages: 5, ms: 1975, ok: true },
  { id: 5, originalName: '起诉状_模板示例.docx', typeName: '金融借款起诉状', at: '2026-10-30 10:00', pages: 4, ms: 1490, ok: true },
  { id: 4, originalName: '起诉状_吴某某.docx', typeName: '金融借款起诉状', at: '2026-10-30 10:01', pages: 4, ms: 1705, ok: true },
  { id: 3, originalName: '起诉状_谭某某.docx', typeName: '金融借款起诉状', at: '2026-10-30 10:02', pages: 4, ms: 1812, ok: true },
  { id: 2, originalName: '民事起诉状（传统）_修订.docx', typeName: '金融借款起诉状', at: '2026-10-30 12:59', pages: 5, ms: 2050, ok: true },
  { id: 1, originalName: '民事起诉状（传统）.docx', typeName: '金融借款起诉状', at: '2026-10-30 13:00', pages: 5, ms: 1888, ok: true },
]

export const DEMO_CONVERT_MAPPING = [
  { from: '原告', to: '原告基本信息（要素 1）' },
  { from: '被告', to: '被告基本信息（要素 2）' },
  { from: '诉讼请求', to: '诉讼请求（要素 3）' },
  { from: '事实与理由', to: '事实与理由（要素 4）' },
  { from: '证据清单', to: '证据（要素 5）' },
  { from: '管辖法院', to: '受诉法院（要素 6）' },
]

export interface ConvertTemplateRow {
  /** 法院文书类型编号（mbid），下拉框里的值就是它 */
  mbid: string
  name: string
  /** 适用的案由 */
  cause: string
  /** 模板版本：法院示范文本改版后旧版本生成的文件会被标「待重转」 */
  version: string
  /** 本月转换次数（展示用，说明哪类文书是主力） */
  monthly: number
}

export const DEMO_CONVERT_TEMPLATES: ConvertTemplateRow[] = [
  { mbid: 'MBID-FL-0102', name: '金融借款合同纠纷起诉状', cause: '金融借款合同纠纷', version: 'v2026.1', monthly: 38 },
  { mbid: 'MBID-LOAN-0211', name: '借款合同纠纷起诉状', cause: '民间借贷纠纷', version: 'v2026.1', monthly: 21 },
  { mbid: 'MBID-CT-0308', name: '信用卡纠纷起诉状', cause: '信用卡纠纷', version: 'v2026.1', monthly: 17 },
  { mbid: 'MBID-GUAR-0405', name: '保证合同纠纷起诉状', cause: '保证合同纠纷', version: 'v2025.2', monthly: 9 },
  { mbid: 'MBID-MORT-0412', name: '抵押合同纠纷起诉状', cause: '抵押合同纠纷', version: 'v2026.1', monthly: 7 },
  { mbid: 'MBID-LEASE-0513', name: '融资租赁合同纠纷起诉状', cause: '融资租赁合同纠纷', version: 'v2026.1', monthly: 6 },
  { mbid: 'MBID-LABOR-0620', name: '劳动争议起诉状', cause: '劳动争议', version: 'v2025.3', monthly: 4 },
  { mbid: 'MBID-CON-0715', name: '买卖合同纠纷起诉状', cause: '买卖合同纠纷', version: 'v2026.1', monthly: 3 },
  { mbid: 'MBID-TORT-0801', name: '机动车交通事故责任纠纷起诉状', cause: '机动车交通事故责任纠纷', version: 'v2026.1', monthly: 2 },
  { mbid: 'MBID-DIV-0907', name: '离婚纠纷起诉状', cause: '离婚纠纷', version: 'v2025.2', monthly: 2 },
  { mbid: 'MBID-APL-1003', name: '民事上诉状', cause: '通用（二审）', version: 'v2026.1', monthly: 2 },
  { mbid: 'MBID-ANS-1009', name: '民事答辩状', cause: '通用（应诉）', version: 'v2026.1', monthly: 1 },
]

export interface ConvertMappingRow {
  /** 要素式文书里的栏位名 */
  from: string
  /** 该栏位在传统起诉状里对应的内容 */
  to: string
  /** 缺了会被法院退回（一张网立案的前置校验） */
  required: boolean
  /** 示例值（脱敏） */
  sample: string
}

export const DEMO_CONVERT_MAPPING_DETAIL: ConvertMappingRow[] = [
  { from: '原告', to: '原告基本信息', required: true, sample: '某某银行广州分行' },
  { from: '被告', to: '被告基本信息', required: true, sample: '谭某某，男，19XX 年生' },
  { from: '诉讼请求', to: '诉讼请求（分项列明）', required: true, sample: '本金 ¥998,670.21 及利息' },
  { from: '事实与理由', to: '事实与理由（按要素分段）', required: true, sample: '20XX 年 XX 月放款 XX 万元' },
  { from: '证据清单', to: '证据（逐份对应事实）', required: true, sample: '借款合同 P1–12、放款凭证 P13' },
  { from: '管辖法院', to: '受诉法院', required: true, sample: '广州市天河区人民法院' },
  { from: '利息计算', to: '利息计算方式与截止日', required: true, sample: '按 LPR 上浮 50%，计至清偿日' },
  { from: '担保情况', to: '担保物权与保证人', required: false, sample: '房产抵押 + 某某公司连带保证' },
  { from: '送达地址', to: '送达地址确认', required: true, sample: '佛山市顺德区某某街道 XX 号' },
  { from: '调解意愿', to: '是否同意调解', required: false, sample: '同意调解' },
  { from: '诉讼费承担', to: '诉讼费用负担请求', required: false, sample: '由被告承担' },
  { from: '附件目录', to: '随附材料清单', required: false, sample: '起诉状副本 2 份、证据 3 组' },
]

export interface ConvertPreviewField {
  label: string
  /** 传统起诉状里的写法（整段叙述） */
  legacy: string
  /** 要素式示范文本里的写法（拆成栏位） */
  elemental: string
  /** 传统写法里是否有对应表述；没有 = 要素式新增的栏位 */
  matched: boolean
}

export const DEMO_CONVERT_PREVIEW: ConvertPreviewField[] = [
  {
    label: '当事人',
    legacy: '原告某某银行广州分行，住所地佛山市顺德区某某街道。负责人黄某某，行长。被告谭某某，男，19XX 年 XX 月 XX 日出生，住佛山市顺德区某某街道。',
    elemental: '原告：某某银行广州分行（统一社会信用代码 91XXXXXXXXXXXXXXXX）\n被告：谭某某（身份证号已脱敏）',
    matched: true,
  },
  {
    label: '诉讼请求',
    legacy: '请求判令被告偿还借款本金 998,670.21 元及相应利息、罚息，并承担本案诉讼费用。',
    elemental: '1. 偿还本金 ¥998,670.21\n2. 支付利息（按 LPR 上浮 50%，自 20XX-XX-XX 计至清偿日）\n3. 诉讼费由被告承担',
    matched: true,
  },
  {
    label: '事实与理由',
    legacy: '20XX 年 XX 月 XX 日，被告与原告签订《个人借款合同》，借款 1,000,000.00 元，期限 36 个月。原告依约放款，被告自 20XX 年 XX 月起未按约还款，至起诉日尚欠本金 998,670.21 元。',
    elemental: '合同签订日：20XX-XX-XX\n放款金额：¥1,000,000.00\n违约起始：20XX-XX\n尚欠本金：¥998,670.21',
    matched: true,
  },
  {
    label: '证据',
    legacy: '证据一《个人借款合同》、证据二放款凭证、证据三还款明细，以上证据证明借款关系成立及被告违约事实。',
    elemental: '证据 1《个人借款合同》P1–12\n证据 2 放款凭证 P13\n证据 3 还款明细 P14–16',
    matched: true,
  },
  {
    label: '利息计算方式',
    legacy: '（传统起诉状通常只写「及相应利息」，具体算法在庭审中主张）',
    elemental: '按 LPR 上浮 50%，自 20XX-XX-XX 计至实际清偿日，暂计至起诉日 ¥86,412.55',
    matched: false,
  },
  {
    label: '是否同意调解',
    legacy: '（传统起诉状无此栏位）',
    elemental: '同意调解。可接受分期，首期不低于 30%。',
    matched: false,
  },
]

export interface ConvertStatSummary {
  /** 累计转换次数 */
  total: number
  /** 本月转换次数 */
  monthly: number
  /** 平均单份耗时（毫秒） */
  avgMs: number
  /** 失败率（百分比，含 403 开关未开、原文件格式不支持） */
  failRate: number
  /** 本月失败次数（与 failRate 对得上，避免两个数字打架） */
  failed: number
}

export const DEMO_CONVERT_STATS: ConvertStatSummary = {
  total: 1584,
  monthly: 112,
  avgMs: 1840,
  failRate: 2.7,
  failed: 3,
}
