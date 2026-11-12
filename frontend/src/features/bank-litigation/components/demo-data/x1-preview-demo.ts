/**
 * 演示数据 · H1. X1 · 扫描件预览 / 置信度因子
 *
 * 上一条线证明「拆得开、转得出」，这一层证明**每一处结论都能点开看依据**：
 * 扫描件预览能翻页，并框出「这一句是在哪认出来的」；98% 的置信度能展开成
 * 4 个因子，各自带分。口径与 stages-demo.ts 同一案件（38 页 · 8 份材料）。
 * `X1PreviewPage` 等版式类型见 `types.ts`。
 * 真实功能上线时整个文件删除即可。
 */

import type { X1PreviewPage } from './types'

export interface X1SegmentPreviewRow {
  seq: number
  pages: X1PreviewPage[]
}

export const DEMO_X1_SEGMENT_PREVIEWS: X1SegmentPreviewRow[] = [
  {
    seq: 1,
    pages: [
      {
        pageNo: 1,
        lines: [
          { kind: 'title', text: '个人购房借款/担保合同' },
          { kind: 'meta', text: '合同编号：DEMO202100000001　　　编号：01' },
          { kind: 'heading', text: '第一条　贷款金额' },
          { kind: 'para', text: '贷款人根据借款人的申请，向借款人发放个人住房贷款，金额为人民币捌拾贰万元整（¥820,000.00）。' },
          { kind: 'heading', text: '第二条　贷款期限' },
          { kind: 'para', text: '贷款期限为 240 个月，自 2019 年 3 月 18 日起至 2039 年 3 月 18 日止。' },
          { kind: 'field', text: '借款人（签字）：谭某某　　　贷款人（盖章）：某某银行某某支行' },
          { kind: 'seal', text: '某某银行某某支行 · 合同专用章' },
        ],
        boxes: [
          { top: 5, left: 26, width: 48, height: 8, label: '这里识别到「个人购房借款/担保合同」' },
          { top: 12, left: 22, width: 56, height: 5, label: '合同编号 DEMO202100000001' },
        ],
      },
      {
        pageNo: 2,
        lines: [
          { kind: 'heading', text: '第四条　贷款利率与计息' },
          { kind: 'para', text: '本合同项下贷款利率按中国人民银行同期同档次贷款基准利率上浮 5% 执行，即年利率 4.90%。' },
          { kind: 'table', text: '期次 | 应还日期 | 应还本息 | 实还 | 逾期天数' },
          { kind: 'table', text: '1 | 2019-04-18 | 5,432.11 | 5,432.11 | 0' },
          { kind: 'table', text: '2 | 2019-05-18 | 5,432.11 | 5,432.11 | 0' },
          { kind: 'sign', text: '（本页为合同正文第 2 页，骑缝章压印右侧）' },
        ],
        boxes: [{ top: 8, left: 8, width: 60, height: 6, label: '这里识别到「第四条　贷款利率与计息」' }],
      },
      {
        pageNo: 3,
        lines: [
          { kind: 'heading', text: '第九条　违约责任' },
          { kind: 'para', text: '借款人未按期归还贷款本息的，贷款人有权按合同约定利率上浮 50% 计收罚息，并宣布贷款提前到期。' },
          { kind: 'heading', text: '第十七条　争议解决' },
          { kind: 'para', text: '因本合同发生的争议，由合同签订地人民法院管辖。合同签订地：广东省佛山市南海区。' },
          { kind: 'sign', text: '借款人：谭某某　　　共同借款人：李某某　　　日期：2019-03-18' },
        ],
        boxes: [{ top: 40, left: 8, width: 62, height: 6, label: '这里识别到管辖约定（签订地法院）' }],
      },
    ],
  },
  {
    seq: 2,
    pages: [
      {
        pageNo: 15,
        lines: [
          { kind: 'title', text: '借款借据' },
          { kind: 'meta', text: '借据编号：JJ20190318001' },
          { kind: 'para', text: '兹借到人民币捌拾贰万元整（¥820,000.00），期限自 2019-03-18 至 2039-03-18。' },
          { kind: 'field', text: '放款日期：2019-03-18　　　放款账号：6210 **** **** 3321' },
          { kind: 'seal', text: '某某银行某某支行 · 业务专用章' },
          { kind: 'sign', text: '借款人（签字）：谭某某' },
        ],
        boxes: [
          { top: 4, left: 30, width: 40, height: 8, label: '这里识别到「借款借据」' },
          { top: 22, left: 8, width: 40, height: 6, label: '放款金额 ¥820,000.00' },
        ],
      },
      {
        pageNo: 16,
        lines: [
          { kind: 'title', text: '放款凭证（银行留存）' },
          { kind: 'table', text: '交易日期 | 摘要 | 交易金额 | 对方账号 | 状态' },
          { kind: 'table', text: '2019-03-18 | 个人住房贷款放款 | 820,000.00 | 6210****3321 | 成功' },
          { kind: 'sign', text: '经办：某某　　复核：某某　　打印时间：2019-03-18 15:22' },
        ],
        boxes: [{ top: 26, left: 6, width: 88, height: 6, label: '这里识别到放款成功流水（820,000.00）' }],
      },
    ],
  },
  {
    seq: 3,
    pages: [
      {
        pageNo: 17,
        lines: [
          { kind: 'title', text: '个人贷款还款明细表' },
          { kind: 'meta', text: '账号：6210 **** **** 3321　　共 84 期' },
          { kind: 'table', text: '期次 | 应还日期 | 应还本息 | 实还 | 逾期天数' },
          { kind: 'table', text: '1 | 2019-04-18 | 5,432.11 | 5,432.11 | 0' },
          { kind: 'table', text: '2 | 2019-05-18 | 5,432.11 | 5,432.11 | 0' },
          { kind: 'table', text: '3 | 2019-06-18 | 5,432.11 | 5,432.11 | 0' },
          { kind: 'table', text: '… | … | … | … | …' },
        ],
        boxes: [{ top: 22, left: 6, width: 88, height: 6, label: '这里识别到表格表头（跨页沿用）' }],
      },
      {
        pageNo: 18,
        lines: [
          { kind: 'table', text: '期次 | 应还日期 | 应还本息 | 实还 | 逾期天数' },
          { kind: 'table', text: '73 | 2025-04-18 | 5,432.11 | 5,432.11 | 0' },
          { kind: 'table', text: '74 | 2025-05-18 | 5,432.11 | 0.00 | 30' },
          { kind: 'table', text: '75 | 2025-06-18 | 5,432.11 | 0.00 | 61' },
          { kind: 'table', text: '… | … | … | … | …' },
        ],
        boxes: [{ top: 14, left: 40, width: 34, height: 6, label: '这里识别到首期逾期（2025-05-18 未还）' }],
      },
    ],
  },
  {
    seq: 4,
    pages: [
      {
        pageNo: 25,
        lines: [
          { kind: 'title', text: '贷款催收记录汇总' },
          { kind: 'meta', text: '统计区间：2024-06-01 至 2025-06-12' },
          { kind: 'table', text: '日期 | 方式 | 对象 | 结果 | 经办' },
          { kind: 'table', text: '2025-06-12 | 电话 | 谭某某 | 未接通 | 某某' },
          { kind: 'table', text: '2025-05-20 | 上门 | 谭某某 | 家属签收通知 | 某某' },
          { kind: 'para', text: '手写批注：客户称近期资金紧张，请求延期，未承诺还款时间。' },
        ],
        boxes: [
          { top: 4, left: 26, width: 48, height: 8, label: '这里识别到「贷款催收记录汇总」' },
          { top: 58, left: 6, width: 70, height: 8, label: '手写批注 OCR 置信度 0.58' },
        ],
      },
      {
        pageNo: 26,
        lines: [
          { kind: 'heading', text: '催收情况小结' },
          { kind: 'para', text: '自逾期之日起，累计电话催收 11 次、上门催收 3 次、书面催收函 2 份。' },
          { kind: 'sign', text: '经办客户经理：王某某　　日期：2025-06-12' },
        ],
        boxes: [{ top: 14, left: 6, width: 80, height: 6, label: '这里识别到催收次数统计（11 次 / 3 次）' }],
      },
    ],
  },
  {
    seq: 5,
    pages: [
      {
        pageNo: 29,
        lines: [
          { kind: 'title', text: '中华人民共和国居民身份证' },
          { kind: 'field', text: '姓名　谭某某　　　性别　男　　　民族　汉' },
          { kind: 'field', text: '出生　1979 年 X 月 X 日' },
          { kind: 'field', text: '住址　广东省佛山市南海区某某路 X 号' },
          { kind: 'field', text: '公民身份号码　4406**********1234' },
          { kind: 'meta', text: '（正反面复印于同一页）' },
        ],
        boxes: [
          { top: 6, left: 14, width: 62, height: 8, label: '这里识别到「居民身份证」' },
          { top: 54, left: 14, width: 62, height: 6, label: '公民身份号码（脱敏显示）' },
        ],
      },
    ],
  },
  {
    seq: 6,
    pages: [
      {
        pageNo: 30,
        lines: [
          { kind: 'title', text: '差额补足承诺函' },
          { kind: 'para', text: '致：某某银行某某支行' },
          { kind: 'para', text: '就谭某某与贵行签订的个人购房借款/担保合同（编号 DEMO202100000001），承诺人自愿为借款人在该合同项下全部债务承担差额补足义务。' },
          { kind: 'para', text: '本承诺函自承诺人签字并加盖公章之日起生效。' },
        ],
        boxes: [{ top: 4, left: 24, width: 50, height: 8, label: '这里识别到「差额补足承诺函」' }],
      },
      {
        pageNo: 31,
        lines: [
          { kind: 'para', text: '承诺人（盖章）：某某置业有限公司' },
          { kind: 'seal', text: '某某置业有限公司 · 公章（压住落款日期）' },
          { kind: 'sign', text: '法定代表人或授权代表（签字）：＿＿＿＿＿' },
          { kind: 'sign', text: '日期：2021-03-__（被印章覆盖）' },
        ],
        boxes: [
          { top: 26, left: 34, width: 34, height: 26, label: '印章压住落款日期，签署日无法确认' },
          { top: 68, left: 8, width: 46, height: 7, label: '这里识别到承诺人名称' },
        ],
      },
    ],
  },
  {
    seq: 7,
    pages: [
      {
        pageNo: 32,
        lines: [
          { kind: 'sign', text: '（手写）' },
          { kind: 'para', text: '小谭：材料先收着，下周把身份证和收入证明补过来。' },
          { kind: 'para', text: '—— 王' },
        ],
        boxes: [{ top: 22, left: 8, width: 60, height: 18, label: '手写体，识别置信度 0.24（疑非案件材料）' }],
      },
    ],
  },
  {
    seq: 8,
    pages: [
      {
        pageNo: 33,
        lines: [
          { kind: 'title', text: '个人活期账户交易明细' },
          { kind: 'meta', text: '账号：6210 **** **** 3321　　区间：2025-01-01 至 2026-04-30' },
          { kind: 'table', text: '日期 | 摘要 | 金额 | 余额' },
          { kind: 'table', text: '2026-01-18 | 代扣 | -5,432.11 | 1,204.88' },
          { kind: 'table', text: '2026-02-18 | 代扣失败 | 0.00 | 1,204.88' },
          { kind: 'table', text: '2026-03-18 | 代扣失败 | 0.00 | 1,204.88' },
        ],
        boxes: [{ top: 22, left: 6, width: 88, height: 6, label: '这里识别到表格表头（第 4-5 页会重复）' }],
      },
      {
        pageNo: 34,
        lines: [
          { kind: 'table', text: '日期 | 摘要 | 金额 | 余额' },
          { kind: 'table', text: '2026-04-18 | 代扣失败 | 0.00 | 1,204.88' },
          { kind: 'para', text: '注：本页表头与上页重复，系统已按表头重新拼表。' },
        ],
        boxes: [{ top: 6, left: 6, width: 60, height: 6, label: '跨页重复表头，已自动拼接' }],
      },
    ],
  },
]

export interface X1ConfidenceFactorRow {
  /** 属于哪一份（对应 DEMO_INTAKE_SEGMENTS.seq） */
  seq: number
  label: string
  /** 该因子在总分里的权重分（与其它因子相加 = round(confidence*100)） */
  score: number
  detail: string
}

export const DEMO_X1_CONFIDENCE_FACTORS: X1ConfidenceFactorRow[] = [
  { seq: 1, label: '标题关键词匹配度', score: 40, detail: '首行命中「个人购房借款/担保合同」标准表述，与「借款合同」类型模板完全一致' },
  { seq: 1, label: '版式特征', score: 28, detail: '条款编号连续（第一至第十七条）、首部编号行在、无跨文混排 —— 与建行标准版式一致' },
  { seq: 1, label: '字体字号', score: 18, detail: '标题 16pt 黑体居中、正文 10.5pt 宋体，符合制式合同排版' },
  { seq: 1, label: '骑缝章位置', score: 12, detail: 'P1–P14 右侧骑缝章连续完整，说明这 14 页确属同一份文件' },

  { seq: 6, label: '标题关键词匹配度', score: 38, detail: '首行命中「差额补足承诺函」，归入「担保文件」' },
  { seq: 6, label: '版式特征', score: 15, detail: '篇幅过短（2 页），缺常见条款段落结构，与模板差异较大' },
  { seq: 6, label: '字体字号', score: 8, detail: '正文为 12pt 宋体（非制式），疑为自行打印后盖章' },
  { seq: 6, label: '骑缝章位置', score: 0, detail: '未见骑缝章；落款公章压住日期，无法确认签署时间' },

  { seq: 7, label: '标题关键词匹配度', score: 6, detail: '无标题、无编号，仅手写一句话，未命中任何类型模板' },
  { seq: 7, label: '版式特征', score: 4, detail: '整页手写体，无表格无条款' },
  { seq: 7, label: '字体字号', score: 9, detail: '非印刷字体，字迹判定为手写（与案件材料惯例不符）' },
  { seq: 7, label: '骑缝章位置', score: 5, detail: '单页无骑缝，右侧无边距压印' },
]
