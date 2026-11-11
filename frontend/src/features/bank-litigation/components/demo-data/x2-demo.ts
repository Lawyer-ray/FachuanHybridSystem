/**
 * 演示数据 · I. X2 · ③ 缺件 / ⑤ 回扫 的细节数据
 *
 * 前缀 DEMO_X2_*：只给 GapPanel / ReturnedPanel 用。
 * 与 stages-demo.ts 里的 DEMO_GAP_* / DEMO_RETURNED_* 是同一批演示数据的
 * **下钻层**：那边是「一行一条」，这里是「这一行的沟通过程、附件、配置」。
 * GapSource / GapTimelineEvent / ScanMailboxConfig / AssignCandidate /
 * MailAttachment / ClaimFilter 这几个共享类型见 `types.ts`。
 * 真实功能上线时整个文件删除即可。
 */

import type {
  AssignCandidate,
  ClaimFilter,
  GapSource,
  GapTimelineEvent,
  MailAttachment,
  ScanMailboxConfig,
} from './types'

export interface GapNoticeSourceRow {
  item: string
  source: GapSource
}

export const DEMO_X2_GAP_SOURCES: GapNoticeSourceRow[] = [
  { item: '催收记录（2025 年后）', source: '催收类' },
  { item: '借款人最新联系方式', source: '身份类' },
  { item: '抵押物权属证明', source: '担保类' },
  { item: '共同借款人身份证明', source: '身份类' },
  { item: '还款账户近半年流水', source: '合同类' },
]

export const DEMO_X2_GAP_TIMELINE: GapTimelineEvent[] = [
  { item: '催收记录（2025 年后）', at: '10-28 14:02', kind: 'system', channel: '系统', title: '检测到缺件，生成补件清单', detail: '必备清单比对：催收类材料止于 2025-06，缺最近 12 个月' },
  { item: '催收记录（2025 年后）', at: '10-28 14:02', kind: 'sms', channel: '短信', title: '补件通知已送达', detail: '发送至 138****6621，含免登录上传链接（有效期 15 天）' },
  { item: '催收记录（2025 年后）', at: '10-28 14:02', kind: 'mail', channel: '邮件', title: '补件通知已送达', detail: 'wangmoumou@某某银行.邮箱，附补件清单 PDF' },
  { item: '催收记录（2025 年后）', at: '10-28 14:05', kind: 'customer', channel: '客户', title: '客户已读通知', detail: '客户经理 王某某 点开短信链接，进入免登录上传页' },
  { item: '催收记录（2025 年后）', at: '10-29 17:40', kind: 'system', channel: '系统', title: '发送 1 次催办', detail: '超过 24 小时未上传，自动发送催办短信' },
  { item: '催收记录（2025 年后）', at: '10-30 09:20', kind: 'customer', channel: '客户', title: '客户上传 2 份材料', detail: '催收记录_补充_2025Q3-Q4.pdf（6 页）、催收记录_补充_说明.txt（1 页）' },
  { item: '催收记录（2025 年后）', at: '10-30 09:22', kind: 'recognize', channel: '系统', title: '系统识别并归案', detail: '识别到电话催收 7 次、上门 2 次，归入「催收记录」槽位' },
  { item: '催收记录（2025 年后）', at: '10-30 09:22', kind: 'system', channel: '系统', title: '重跑缺件检测', detail: '该项由「硬阻塞」转为「已补齐」，硬阻塞剩 3 项' },

  { item: '借款人最新联系方式', at: '10-28 14:02', kind: 'system', channel: '系统', title: '检测到缺件，生成补件清单', detail: '合同留存电话已停用，送达地址需更新' },
  { item: '借款人最新联系方式', at: '10-28 14:03', kind: 'wechat', channel: '微信', title: '补件通知已推送到企业微信', detail: '发送至客户经理 王某某（已读回执 14:06）' },
  { item: '借款人最新联系方式', at: '10-30 09:18', kind: 'customer', channel: '客户', title: '客户微信发来文本', detail: '客户补充信息.txt —— 新手机号与现住址' },
  { item: '借款人最新联系方式', at: '10-30 09:22', kind: 'recognize', channel: '系统', title: '系统识别并回填', detail: '手机号 138****XXXX，现住址写入送达地址栏' },

  { item: '抵押物权属证明', at: '10-28 14:02', kind: 'system', channel: '系统', title: '检测到缺件，生成补件清单', detail: '合同约定抵押，但未见不动产权证复印件' },
  { item: '抵押物权属证明', at: '10-28 14:02', kind: 'sms', channel: '短信', title: '补件通知已送达', detail: '发送至 138****6621（硬阻塞项，单独标红）' },
  { item: '抵押物权属证明', at: '10-28 14:09', kind: 'customer', channel: '客户', title: '客户已读通知', detail: '客户回复「产权证在抵押人手上，需向其索取」' },
  { item: '抵押物权属证明', at: '10-29 17:40', kind: 'system', channel: '系统', title: '发送 1 次催办', detail: '仍未见上传，催办短信已发出' },
  { item: '抵押物权属证明', at: '10-31 10:12', kind: 'customer', channel: '客户', title: '客户反馈进度', detail: '已联系抵押人，预计 11-03 前取得扫描件' },

  { item: '共同借款人身份证明', at: '10-28 14:02', kind: 'system', channel: '系统', title: '检测到缺件，生成补件清单', detail: '合同列明两位借款人，仅见一人身份证' },
  { item: '共同借款人身份证明', at: '10-28 14:02', kind: 'sms', channel: '短信', title: '补件通知已送达', detail: '发送至 138****6621（硬阻塞项，单独标红）' },
  { item: '共同借款人身份证明', at: '10-28 14:09', kind: 'customer', channel: '客户', title: '客户已读通知', detail: '客户回复「共同借款人李某某出差，下周回传」' },
  { item: '共同借款人身份证明', at: '10-30 15:30', kind: 'system', channel: '系统', title: '发送 1 次催办', detail: '仍未见上传，催办短信 + 邮件双通道' },
  { item: '共同借款人身份证明', at: '11-01 08:50', kind: 'customer', channel: '客户', title: '客户反馈进度', detail: '李某某已拍照，待其本人确认后上传' },

  { item: '还款账户近半年流水', at: '10-30 09:15', kind: 'system', channel: '系统', title: '补录：客户补传后仍缺最近一期', detail: '已有流水止于 2026-04，建议补至起诉前一月' },
  { item: '还款账户近半年流水', at: '10-30 09:15', kind: 'mail', channel: '邮件', title: '补件通知已送达', detail: 'admin@某某律所.邮箱，仅走邮件（一般项不打扰客户）' },
  { item: '还款账户近半年流水', at: '10-30 11:02', kind: 'customer', channel: '客户', title: '客户已读通知', detail: '行政 陈某某 已转告客户经理' },
]

export interface GapScriptRow {
  id: string
  severity: '硬阻塞' | '一般' | '催办' | '回执'
  title: string
  body: string
}

export const DEMO_X2_GAP_SCRIPTS: GapScriptRow[] = [
  { id: 'blocker', severity: '硬阻塞', title: '影响立案的缺件', body: '【影响立案的缺件】您好，本案还有 {n} 项材料缺失将无法立案：{list}。请点此链接上传（免登录）：{link}，或直接微信发给经办律师。' },
  { id: 'normal', severity: '一般', title: '建议补充的材料', body: '【建议补充的材料】您好，以下材料建议补充，不影响先立案：{list}。回复本邮件即可传附件。' },
  { id: 'urge', severity: '催办', title: '补件催办提醒', body: '【补件催办】您还有 {n} 项材料未补齐，已超 {days} 天。为不影响立案进度，请尽快上传：{link}' },
  { id: 'receipt', severity: '回执', title: '已收妥确认', body: '【已收妥】您补交的 {n} 份材料已收到并归档，无需再重复提交。感谢配合。' },
]

export const DEMO_X2_SCAN_MAILBOXES: ScanMailboxConfig[] = [
  { addr: 'courts@某某律所.邮箱', note: '一张网收件箱 · 法院送达文书', count: 128, interval: '5 分钟', folder: 'INBOX / 送达文书', whitelist: '*.court.gov.cn、12368 短信转发' },
  { addr: 'admin@某某律所.邮箱', note: '行政扫描仪自动转发', count: 42, interval: '10 分钟', folder: 'INBOX / scan', whitelist: 'scanner@某某律所.邮箱' },
  { addr: 'client@某某律所.邮箱', note: '客户往来附件', count: 67, interval: '5 分钟', folder: 'INBOX', whitelist: '已签约客户域 · 共 24 个地址' },
]

export const DEMO_X2_SCAN_INTERVALS = ['1 分钟', '5 分钟', '15 分钟', '1 小时'] as const

export const DEMO_X2_ASSIGN_CANDIDATES: AssignCandidate[] = [
  { name: '谭某某金融借款', caseNo: '（20XX）粤0106民初XXXX号', court: '广州市天河区人民法院', party: '某某银行某某支行 诉 谭某某、李某某', slots: ['律师函签收回执', '送达地址确认书', '催收记录', '还款明细'] },
  { name: '谭某某金融借款（诉前调解）', caseNo: '（20XX）粤0606民初XXXX号', court: '佛山市禅城区人民法院', party: '某某银行某某支行 诉 谭某某', slots: ['调解笔录', '催收记录', '还款明细'] },
  { name: '李某某信用卡纠纷', caseNo: '（20XX）粤0106民初XXXX号', court: '广州市天河区人民法院', party: '某某银行某某支行 诉 李某某', slots: ['信用卡对账单', '催收记录'] },
  { name: '某某贸易公司保证合同纠纷', caseNo: '（20XX）粤0106民初XXXX号', court: '广州市天河区人民法院', party: '某某银行某某支行 诉 某某贸易公司', slots: ['保证合同', '送达地址确认书'] },
]

export const DEMO_X2_MAIL_ATTACHMENTS: MailAttachment[] = [
  { subject: 'Re: 谭某某案 补充材料', name: '催收记录_补充_2025Q3-Q4.pdf', size: '1.2 MB', kind: 'pdf', pages: 6, slot: '催收记录' },
  { subject: 'Re: 谭某某案 补充材料', name: '客户补充信息.txt', size: '1.6 MB', kind: 'pdf', pages: 1, slot: '送达地址' },
  { subject: '扫描件-不动产权证', name: '不动产权证_扫描件.pdf', size: '2.0 MB', kind: 'pdf', pages: 4, slot: '抵押物权属证明' },
  { subject: '（20XX）粤0106民初XXXX号 受理通知书', name: '受理通知书.jpg', size: '2.4 MB', kind: 'image', pages: 1, slot: '法院文书' },
  { subject: 'FW: 律师函签收回执', name: '律师函签收回执.pdf', size: '2.8 MB', kind: 'pdf', pages: 2, slot: '律师函签收回执' },
]

export const DEMO_X2_CLAIM_FILTERS: ClaimFilter[] = ['全部', '自动归案', '待人工', '已标记无关']
