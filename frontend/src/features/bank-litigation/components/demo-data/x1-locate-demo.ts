/**
 * 演示数据 · H2. X1 · 原文对照 / 字段出处 / 追加渠道 / 转换方法
 *
 * 全文能从渲染视图切到源码/原文对照，关键字段能逐条校对；追加材料三种来源
 * 与四种转换方法可切换。口径与 stages-demo.ts 同一案件。
 * 真实功能上线时整个文件删除即可。
 */

export interface X1AppendChannelRow {
  key: 'link' | 'upload' | 'mail'
  name: string
  desc: string
  detail: string
  /** 这个渠道现成的待取清单（展示用） */
  items: string[]
}

export const DEMO_X1_APPEND_CHANNELS: X1AppendChannelRow[] = [
  {
    key: 'link',
    name: '从客户链接',
    desc: '客户通过免登录链接上传，链接本身即凭证',
    detail: '刚刚有一条新上传待拉取',
    items: ['催收记录_补充_2025Q3-Q4.pdf · 6 页 · 10-30 09:20', '客户补充信息.txt · 1 页 · 10-30 09:22'],
  },
  {
    key: 'upload',
    name: '从本地上传',
    desc: '律师自己从电脑选文件，支持 PDF / 图片 / xlsx',
    detail: '可一次多选，单个 ≤ 50 MB',
    items: [],
  },
  {
    key: 'mail',
    name: '从邮箱拉取',
    desc: '扫指定邮箱的附件，按案号/当事人自动匹配到本案',
    detail: '近 7 天有 3 封带附件的邮件命中本案',
    items: ['Re: 谭某某案 补充材料 · 2 个附件 · 11-01 09:12', '扫描件-不动产权证 · 1 个附件 · 11-01 10:05'],
  },
]

export interface X1OriginalCompareRow {
  /** markdown 侧的文本（与 DEMO_UNDERSTAND_DOCS.excerpt 里的句子对得上） */
  md: string
  /** 扫描件侧看起来的样子 */
  scan: string
  /** 扫描侧的可信度（OCR 没认清的用 low，画虚线下划线） */
  fidelity: 'high' | 'low'
  page: number
}

export const DEMO_X1_ORIGINAL_COMPARE: Record<string, X1OriginalCompareRow[]> = {
  个人购房借款担保合同: [
    { md: '## 个人购房借款/担保合同', scan: '个人购房借款/担保合同', fidelity: 'high', page: 1 },
    { md: '**合同编号**：DEMO202100000001', scan: '合同编号：DEMO202100000001', fidelity: 'high', page: 1 },
    { md: '**借款人**：谭某某', scan: '借款人：谭某某', fidelity: 'high', page: 1 },
    { md: '**贷款人**：某某银行某某支行', scan: '贷款人：某某银行某某支行', fidelity: 'high', page: 1 },
    { md: '### 第一条 贷款金额', scan: '第一条 贷款金额', fidelity: 'high', page: 1 },
    { md: '贷款金额为人民币 **820,000.00 元**（大写：捌拾贰万元整）。', scan: '贷款金额为人民币 820,000.00 元（大写：捌拾贰万元整）。', fidelity: 'low', page: 1 },
  ],
  借款借据及放款凭证: [
    { md: '## 借款借据', scan: '借款借据', fidelity: 'high', page: 15 },
    { md: '兹借到人民币 820,000.00 元，期限自 2019-03-18 至 2039-03-18。', scan: '兹借到人民币 820,000.00 元，期限自 2019-03-18 至 2039-03-18。', fidelity: 'high', page: 15 },
    { md: '放款日期：2019-03-18　放款账号：6210 **** **** 3321', scan: '放款日期：2019-03-18　放款账号：6210 **** **** 3321', fidelity: 'low', page: 15 },
  ],
  '还款明细表（2019-2026）': [
    { md: '## 还款明细', scan: '个人贷款还款明细表', fidelity: 'high', page: 17 },
    { md: '| 期次 | 应还日期 | 应还本息 | 实还 | 逾期天数 |', scan: '期次 | 应还日期 | 应还本息 | 实还 | 逾期天数', fidelity: 'high', page: 17 },
    { md: '| 1 | 2019-04-18 | 5,432.11 | 5,432.11 | 0 |', scan: '1 | 2019-04-18 | 5,432.11 | 5,432.11 | 0', fidelity: 'high', page: 17 },
    { md: '| 85 | 2026-04-18 | 5,432.11 | 0.00 | 198 |', scan: '85 | 2026-04-18 | 5,432.11 | 0.00 | 198', fidelity: 'low', page: 24 },
  ],
  还款账户流水: [
    { md: '## 账户交易明细', scan: '个人活期账户交易明细', fidelity: 'high', page: 33 },
    { md: '| 日期 | 摘要 | 金额 | 余额 |', scan: '日期 | 摘要 | 金额 | 余额', fidelity: 'high', page: 33 },
    { md: '| 2026-01-18 | 代扣 | -5,432.11 | 1,204.88 |', scan: '2026-01-18 | 代扣 | -5,432.11 | 1,204.88', fidelity: 'high', page: 33 },
    { md: '| 2026-02-18 | 代扣失败 | 0.00 | 1,204.88 |', scan: '2026-02-18 | 代扣失.. | 0.00 | 1,204.88', fidelity: 'low', page: 34 },
  ],
}

export interface X1FieldLocateRow {
  doc: string
  field: string
  page: number
  /** 原文上下文（3 行，中间那行是命中行） */
  context: [string, string, string]
  /** 命中行里被抽中的那段文字（用于高亮） */
  hit: string
  /** 机器抽取的口径说明 */
  rule: string
}

export const DEMO_X1_FIELD_LOCATES: X1FieldLocateRow[] = [
  {
    doc: '借款合同', field: '合同编号', page: 1, hit: 'DEMO202100000001',
    context: ['个人购房借款/担保合同', '合同编号：DEMO202100000001　　编号：01', '第一条　贷款金额'],
    rule: '首部「合同编号：」后第一个连续字母数字串',
  },
  {
    doc: '借款合同', field: '借款人', page: 1, hit: '谭某某',
    context: ['贷款人（盖章）：某某银行某某支行', '借款人（签字）：谭某某', '共同借款人（签字）：李某某'],
    rule: '当事人栏「借款人（签字）」后的人名，遇「共同借款人」即停',
  },
  {
    doc: '借款合同', field: '贷款金额', page: 1, hit: '820,000.00',
    context: ['第一条　贷款金额', '贷款金额为人民币 820,000.00 元（大写：捌拾贰万元整）。', '第二条　贷款期限'],
    rule: '「第一条 贷款金额」段落内的小写金额，须与大写金额互校',
  },
  {
    doc: '借款合同', field: '借款期限', page: 1, hit: '2019-03-18 至 2039-03-18',
    context: ['第二条　贷款期限', '贷款期限为 240 个月，自 2019 年 3 月 18 日起至 2039 年 3 月 18 日止。', '第三条　还款方式'],
    rule: '「自…起至…止」两端日期，与 240 个月互校',
  },
  {
    doc: '借款合同', field: '年利率', page: 2, hit: '4.90%',
    context: ['第四条　贷款利率与计息', '本合同项下贷款利率按基准利率上浮 5% 执行，即年利率 4.90%。', '第五条　还款方式'],
    rule: '「年利率」后紧跟的百分数；若与本句内其它百分数冲突则降置信度',
  },
  {
    doc: '借款合同', field: '逾期罚息', page: 3, hit: '上浮 50%',
    context: ['第九条　违约责任', '借款人未按期归还贷款本息的，贷款人有权按合同约定利率上浮 50% 计收罚息。', '第十条　提前到期'],
    rule: '「违约」「罚息」段落内的上浮比例',
  },
  {
    doc: '借款合同', field: '管辖法院', page: 3, hit: '合同签订地人民法院',
    context: ['第十七条　争议解决', '因本合同发生的争议，由合同签订地人民法院管辖。合同签订地：广东省佛山市南海区。', '（以下无正文）'],
    rule: '「争议解决」段落内的管辖表述；「签订地」需另查合同首部比对',
  },
  {
    doc: '还款明细', field: '已还期数', page: 24, hit: '84 期',
    context: ['还款明细表（第 8 页 / 共 8 页）', '累计还款期数：84 期　　累计实还本息：456,297.24 元', '制表日期：2026-05-06'],
    rule: '末页汇总行「累计还款期数」，与表格行数交叉验证',
  },
  {
    doc: '还款明细', field: '逾期期数', page: 18, hit: '12 期',
    context: ['期次 | 应还日期 | 应还本息 | 实还 | 逾期天数', '74 | 2025-05-18 | 5,432.11 | 0.00 | 30', '…（自本期起连续未还）'],
    rule: '「实还 = 0.00」的行数统计',
  },
  {
    doc: '还款明细', field: '最后还款日', page: 24, hit: '2026-04-18',
    context: ['期次 | 应还日期 | 应还本息 | 实还 | 逾期天数', '85 | 2026-04-18 | 5,432.11 | 0.00 | 198', '备注：本行为最后一期，尚未到期已提前宣告到期'],
    rule: '表格末行的「应还日期」',
  },
  {
    doc: '催收记录', field: '催收次数', page: 26, hit: '11 次',
    context: ['催收情况小结', '自逾期之日起，累计电话催收 11 次、上门催收 3 次、书面催收函 2 份。', '经办客户经理：王某某　　日期：2025-06-12'],
    rule: '小结段里的次数统计；与明细表逐条计数互校',
  },
  {
    doc: '催收记录', field: '最后催收日', page: 25, hit: '2025-06-12',
    context: ['日期 | 方式 | 对象 | 结果 | 经办', '2025-06-12 | 电话 | 谭某某 | 未接通 | 某某', '（明细表首行，按日期倒序）'],
    rule: '明细表首行的日期（表按倒序排列）',
  },
]

export interface X1ConvertMethodRow {
  key: string
  name: string
  desc: string
  /** 这个方法大概要多久 */
  ms: number
  /** 对哪类材料效果最好 */
  best: string
}

export const DEMO_X1_CONVERT_METHODS: X1ConvertMethodRow[] = [
  { key: 'native', name: '原生 PDF 文字层', desc: '直接抽取内嵌文字，不做图像识别', ms: 700, best: '电子版生成的 PDF' },
  { key: 'ocr', name: 'OCR 全文识别', desc: '整页当图片识别，再按版式还原段落', ms: 1500, best: '扫描件、拍照件' },
  { key: 'table', name: '表格结构还原', desc: '识别表格线，按单元格还原成 markdown 表', ms: 1100, best: '明细表、流水、对账单' },
  { key: 'ocr-plus', name: 'OCR + 人工校对增强', desc: 'OCR 后再跑一遍印章/手写分离，慢但准', ms: 1900, best: '盖骑缝章、有手写批注的件' },
]
