/**
 * 演示数据 · B1. OA 立案
 *
 * `components/oa/` 下的面板只读这些常量，不做任何业务判断。
 * 站点清单的 `OASiteRow` 见 `types.ts`（被 OA 站点面板与类型声明共用）。
 * 真实功能上线时整个文件删除即可。
 */

import type { OASiteRow } from './types'

export interface OAFilingLogRow {
  stage: string
  message: string
  ms: number
  ok: boolean
  at: string
}

export const DEMO_OA_FILING_LOG: OAFilingLogRow[] = [
  { stage: '登录', message: '使用配置账号登录 OA 成功', ms: 1840, ok: true, at: '11-03 10:02' },
  { stage: '建卷', message: '打开「收案登记」页面，选择案件类别「诉讼」', ms: 960, ok: true, at: '11-03 10:02' },
  { stage: '校验', message: '会话失效，前往登录页重新认证', ms: 4100, ok: false, at: '11-03 10:02' },
  { stage: '重试', message: '第 1 次重试：清理 Cookie 后重新登录成功', ms: 2260, ok: true, at: '11-03 10:02' },
  { stage: '填表', message: '写入案由 / 委托人 / 主办律师（3 项）', ms: 1240, ok: true, at: '11-03 10:03' },
  { stage: '填表', message: '写入标的额 / 收费方式 / 委托人类型（3 项）', ms: 890, ok: true, at: '11-03 10:03' },
  { stage: '关联', message: '关联委托合同 391 与承案团队', ms: 780, ok: true, at: '11-03 10:03' },
  { stage: '上传', message: '上传委托代理合同（扫描件）1 份，2.4 MB', ms: 3120, ok: true, at: '11-03 10:03' },
  { stage: '提交', message: '提交收案登记单，等待 OA 审批流', ms: 1140, ok: true, at: '11-03 10:03' },
  { stage: '轮询', message: '审批流第 1 节点（立案登记）已通过', ms: 4200, ok: true, at: '11-03 10:03' },
  { stage: '回写', message: '取回所内案号 2026-民-XXXX，已落库', ms: 620, ok: true, at: '11-03 10:03' },
  { stage: '收尾', message: '关闭浏览器上下文，会话结束', ms: 180, ok: true, at: '11-03 10:03' },
]

export const DEMO_OA_SITES: OASiteRow[] = [
  { name: '某某律所 OA', credential: true, lastUsed: '11-03 10:03', filedThisMonth: 42, avgMs: '48 s', loginAt: '11-03 10:02', status: 'ok' },
  { name: '某某律所 OA（备用线路）', credential: true, lastUsed: '11-02 16:41', filedThisMonth: 6, avgMs: '1 m 12 s', loginAt: '11-02 16:40', status: 'ok' },
  { name: '分所 OA（诉讼）', credential: true, lastUsed: '11-01 09:18', filedThisMonth: 11, avgMs: '55 s', loginAt: '11-01 09:17', status: 'ok' },
  { name: '分所 OA（测试）', credential: false, lastUsed: '10-28 15:02', filedThisMonth: 0, avgMs: '—', loginAt: '10-28 15:01', status: 'expired' },
  { name: '某某律所 OA（归档专用）', credential: true, lastUsed: '10-26 11:33', filedThisMonth: 3, avgMs: '37 s', loginAt: '10-26 11:32', status: 'ok' },
]

export interface OAFilingHistoryRow {
  caseNo: string
  client: string
  amount: string
  oaCaseNo: string
  state: 'filed' | 'pending' | 'returned'
  cost: string
  at: string
}

export const DEMO_OA_HISTORY: OAFilingHistoryRow[] = [
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥998,670.21', oaCaseNo: 'OA-2026-0418', state: 'filed', cost: '48 s', at: '11-03 10:03' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥642,300.00', oaCaseNo: 'OA-2026-0417', state: 'filed', cost: '51 s', at: '11-03 09:26' },
  { caseNo: '2026-民-XXXX', client: '某某小额贷款公司', amount: '¥331,880.40', oaCaseNo: 'OA-2026-0415', state: 'pending', cost: '—', at: '11-02 17:52' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥1,204,512.00', oaCaseNo: 'OA-2026-0412', state: 'filed', cost: '1 m 12 s', at: '11-02 16:41' },
  { caseNo: '2026-民-XXXX', client: '某某融资担保公司', amount: '¥86,400.00', oaCaseNo: '—', state: 'returned', cost: '2 m 04 s', at: '11-02 14:03' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥475,020.75', oaCaseNo: 'OA-2026-0408', state: 'filed', cost: '44 s', at: '11-01 15:10' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥738,900.00', oaCaseNo: 'OA-2026-0406', state: 'filed', cost: '55 s', at: '11-01 09:18' },
  { caseNo: '2026-民-XXXX', client: '某某资产管理公司', amount: '¥2,015,600.00', oaCaseNo: 'OA-2026-0402', state: 'filed', cost: '1 m 26 s', at: '10-31 16:44' },
  { caseNo: '2026-民-XXXX', client: '某某小额贷款公司', amount: '¥59,800.00', oaCaseNo: 'OA-2026-0399', state: 'filed', cost: '39 s', at: '10-31 11:07' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥512,340.66', oaCaseNo: '—', state: 'returned', cost: '1 m 48 s', at: '10-30 18:12' },
  { caseNo: '2026-民-XXXX', client: '某某融资担保公司', amount: '¥298,000.00', oaCaseNo: 'OA-2026-0391', state: 'filed', cost: '47 s', at: '10-30 10:35' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥1,680,000.00', oaCaseNo: 'OA-2026-0386', state: 'filed', cost: '1 m 03 s', at: '10-29 14:20' },
]

export interface OAFieldMappingRow {
  from: string
  to: string
  /** 取值来源：案件数据 / 委托合同 / 系统推断 / 手工补录 */
  source: 'case' | 'contract' | 'infer' | 'manual'
}

export const DEMO_OA_FIELD_MAPPING: OAFieldMappingRow[] = [
  { from: '案由', to: '案件类别 / 案由', source: 'case' },
  { from: '委托人', to: '委托人名称', source: 'contract' },
  { from: '委托人类型', to: '委托人身份（法人/自然人）', source: 'infer' },
  { from: '主办律师', to: '承办律师', source: 'case' },
  { from: '承案团队', to: '承办部门', source: 'infer' },
  { from: '标的额', to: '争议标的金额', source: 'case' },
  { from: '收费方式', to: '收费方式（计时/计件/风险）', source: 'contract' },
  { from: '合同编号', to: '关联委托合同号', source: 'contract' },
  { from: '管辖法院', to: '受理机关', source: 'case' },
  { from: '对方当事人', to: '对方当事人名称', source: 'case' },
  { from: '收案日期', to: '收案日期', source: 'infer' },
  { from: '所内案号', to: 'OA 案号（执行后回填）', source: 'manual' },
]

export interface OAFailureCause {
  cause: string
  /** 触发位置：登录 / 填表 / 提交 / 轮询 */
  stage: string
  /** 最近 30 天出现次数 */
  hits: number
  advice: string
  /** 是否可由系统自动重试 */
  autoRetry: boolean
}

export const DEMO_OA_FAILURE_CAUSES: OAFailureCause[] = [
  {
    cause: '凭证过期',
    stage: '登录',
    hits: 3,
    advice: '到「设置 → OA 站点」重新录入密码；系统会自动重试 1 次，仍失败需人工更新。',
    autoRetry: true,
  },
  {
    cause: '页面改版',
    stage: '填表',
    hits: 2,
    advice: 'OA 表单字段顺序变了，选择器失配。联系管理员更新站点适配脚本，不要反复重试。',
    autoRetry: false,
  },
  {
    cause: '验证码拦截',
    stage: '登录',
    hits: 1,
    advice: '连续登录触发图形验证码。等待 10 分钟后重试，或改走备用线路站点。',
    autoRetry: true,
  },
  {
    cause: '字段校验不通过',
    stage: '提交',
    hits: 4,
    advice: '多为标的额与受理机关为空。到「起诉条件」补齐后重新发起，源数据缺项重试无效。',
    autoRetry: false,
  },
  {
    cause: 'OA 审批流卡住',
    stage: '轮询',
    hits: 2,
    advice: '收案登记单已提交但审批未流转。到 OA 里手动催办，法穿不再重复提交。',
    autoRetry: false,
  },
  {
    cause: '附件上传超时',
    stage: '上传',
    hits: 1,
    advice: '扫描件超过 20 MB 时容易超时。压缩后重试，或先在 OA 里手工上传再回落单号。',
    autoRetry: true,
  },
]
