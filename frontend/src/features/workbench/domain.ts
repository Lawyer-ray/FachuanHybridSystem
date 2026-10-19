import { dateKey } from '@/lib/date'

import type {
  CaseListItem,
  ContractListItem,
  DealCase,
  DealParty,
  DealTeamMember,
  LawyerListItem,
  WorkbenchDeal,
} from './types'

/** 诉讼类 case_type 代码集合（其余视为非诉） */
export const LITIGATION_TYPES = new Set(['civil', 'criminal', 'administrative', 'labor', 'intl'])

/* ============ 基础格式化 ============ */

export function fmtMoney(v: number | string | null | undefined): string | null {
  if (v == null || v === '' || Number(v) === 0) return null
  return '¥' + Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

export function daysFromToday(dateStr: string | null | undefined, today: Date): number | null {
  if (!dateStr) return null
  const [y, m, d] = dateStr.split('-')
  if (y == null || m == null || d == null) return null
  return Math.round((new Date(+y, +m - 1, +d).getTime() - today.getTime()) / 86400000)
}

/** 相对到期表述：今日到期 / 已到期 N 天 / 剩 N 天 / 剩 N 个月 */
export function relDue(daysLeft: number | null): string {
  if (daysLeft == null) return ''
  if (daysLeft === 0) return '今日到期'
  if (daysLeft < 0) return '已到期 ' + -daysLeft + ' 天'
  if (daysLeft <= 60) return '剩 ' + daysLeft + ' 天'
  return '剩 ' + Math.round(daysLeft / 30) + ' 个月'
}

/**
 * 后端日期统一是 ISO 中划线（2026-09-01 或带时间的 2026-09-01T09:00:00Z），
 * 展示层统一转标准年月日「2026年9月1日」；不像日期的原样返回，不吞值。
 */
export function fmtCNDate(v: string | null | undefined): string {
  if (!v) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v)
  if (!m) return v
  return m[1] + '年' + Number(m[2]) + '月' + Number(m[3]) + '日'
}

/* ============ 三源合并：合同 × 案件 × 律师 → WorkbenchDeal ============ */

/** 案件 → 抽屉域模型（明细按需加载后调用） */
export function buildDealCases(cases: CaseListItem[], today: Date): DealCase[] {
  return cases.map((x) => ({
    id: x.id,
    name: x.name,
    proc: x.current_stage || '未立案',
    ref: x.case_numbers[0]?.number ?? '',
    numbers: x.case_numbers.map((n) => n.number),
    st: x.status || '',
    done: x.status === '已结案',
    auth: x.supervising_authorities[0]?.name ?? '',
    auths: x.supervising_authorities.map((a) => a.name + '（' + (a.authority_type_display || '') + '）'),
    cause: x.cause_of_action || '',
    target: x.target_amount != null ? Number(x.target_amount) : null,
    preserv: x.preservation_amount != null ? Number(x.preservation_amount) : null,
    from: x.start_date || '',
    partyRows: x.parties.map((p) => (p.legal_status || '') + '：' + (p.client_detail?.name || '')),
    parties: x.parties.map((p) => ({ status: p.legal_status || '', name: p.client_detail?.name || '' })),
    logs: [...x.logs]
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
      .map((l) => ({
        when: (l.created_at || '').slice(0, 16),
        who: l.actor_detail?.real_name || l.actor_detail?.username || '',
        text: l.content || '',
        attN: l.attachments.length,
        rem: l.reminder_time ? l.reminder_time.slice(0, 10) + ' 到期提醒' : '',
        remToday: !!l.reminder_time && l.reminder_time.slice(0, 10) === dateKey(today),
      })),
    logReminders: x.logs.flatMap((l) => l.reminders),
    contacts: x.contacts.map((t) => ({
      name: t.name,
      role: t.role_display || '',
      phone: t.phone || '',
      note: t.note || '',
      stage: t.stage_display || '',
      authority: t.authority_name || '',
      address: t.address || '',
    })),
  }))
}

export function buildDeals(
  contracts: ContractListItem[],
  lawyers: LawyerListItem[],
  today: Date,
): WorkbenchDeal[] {
  const lawyerMap = new Map(lawyers.map((l) => [l.id, l]))

  return contracts.map((c) => {
    const lit = LITIGATION_TYPES.has(c.case_type)
    const mine = c.contract_parties.filter((p) => p.client_detail?.is_our_client)
    const other = c.contract_parties.filter(
      (p) => p.role_label === '对方当事人' || (p.client_detail && !p.client_detail.is_our_client),
    )
    const daysLeft = daysFromToday(c.end_date, today)

    const team: DealTeamMember[] = c.assignments.map((a) => {
      const det = lawyerMap.get(a.lawyer_id)
      return {
        name: a.lawyer_name || det?.real_name || '',
        primary: a.is_primary,
        phone: det?.phone || '',
        license: (det?.license_no || '').trim(),
        firm: det?.law_firm_detail?.name || '',
      }
    })

    return {
      id: c.id,
      lit,
      caseType: c.case_type,
      client: c.name,
      ctype: c.case_type_label || c.case_type || '',
      no: c.law_firm_oa_case_number || '',
      amount: fmtMoney(c.fixed_amount),
      amountNum: c.fixed_amount != null ? Number(c.fixed_amount) : null,
      fee: c.fee_mode || '',
      from: c.start_date || '',
      to: c.end_date || '',
      daysLeft,
      status: c.status,
      statusLabel: c.status_label || '',
      specified: c.specified_date || '',
      isFiled: c.is_filed,
      filingNo: c.filing_number || '',
      oaUrl: c.law_firm_oa_url || '',
      customTerms: c.custom_terms || '',
      parties: {
        client: mine[0]?.client_detail?.name ?? '',
        other: other[0]?.client_detail?.name ?? '',
      },
      partiesAll: c.contract_parties.map((p) => {
        const cd = p.client_detail
        return {
          name: cd?.name || '',
          role: p.role_label || '',
          idno: cd?.id_number || '',
          legalRep: cd?.legal_representative || '',
          phone: cd?.phone || '',
          address: cd?.address || '',
          ours: !!cd?.is_our_client,
        }
      }),
      team,
      primaryPhone: c.primary_lawyer?.phone || '',
      caseCount: c.case_count ?? 0,
      work: c.reminders.map((r) => ({
        t: r.content,
        dueFull: fmtCNDate(r.due_at),
        type: r.reminder_type_label || '',
      })),
      riskRate: c.risk_rate ?? null,
      stages: c.representation_stages || [],
      primary: c.primary_lawyer?.real_name || '',
      lawFirm: c.primary_lawyer?.law_firm_name || '',
      totalReceived: fmtMoney(c.total_received),
      totalInvoiced: fmtMoney(c.total_invoiced),
      unpaid: fmtMoney(c.unpaid_amount),
      payments: c.payments,
      payRecords: c.client_payment_records,
      supps: c.supplementary_agreements,
    }
  })
}

/* ============ 筛选 / 排序 / 分组 ============ */

/* ============ 分组（服务端分页后按页内分组；排序已由后端「离今天最近」完成） ============ */

export interface DealGroup {
  /** 节标题：争议解决 / 非诉 */
  title: string
  lit: boolean
  deals: WorkbenchDeal[]
}

/**
 * 按业务形态分两节：争议解决（诉讼/仲裁，有程序链）在前、非诉（专项/常法）在后，
 * 节内保持后端「离今天最近」排序。争议领域（民商事/刑事/行政…）不参与分区，
 * 只作行内标签与筛选维度——领域不改变工作节奏，业务形态才改变。
 */
export function groupDeals(list: WorkbenchDeal[]): DealGroup[] {
  const groups: DealGroup[] = [
    { title: '争议解决', lit: true, deals: list.filter((d) => d.lit) },
    { title: '非诉', lit: false, deals: list.filter((d) => !d.lit) },
  ]
  return groups.filter((g) => g.deals.length > 0)
}

/* ============ 当事人 / 律师复制文本（首行只放名字，粘进文书不用再删括号） ============ */

export function partyCopyText(p: DealParty): string {
  const lines = [p.name]
  if (p.legalRep) lines.push('法定代表人：' + p.legalRep)
  if (p.idno) lines.push('证件号：' + p.idno)
  if (p.phone) lines.push('电话：' + p.phone)
  if (p.address) lines.push('地址：' + p.address)
  return lines.join('\n')
}

export function lawyerCopyText(t: DealTeamMember, d: WorkbenchDeal): string {
  const lines = [t.name]
  const tel = t.phone || (t.primary ? d.primaryPhone : '')
  if (tel) lines.push('电话：' + tel)
  if (t.license) lines.push('执业证号：' + t.license)
  const firm = t.firm || (t.primary ? d.lawFirm : '')
  if (firm) lines.push('律所：' + firm)
  return lines.join('\n')
}

/* ============ 合同抽屉（DealSheet）展示数据 ============ */

/** 合同要素键值行（空值过滤后展示；日期转年月日，到期带相对表述） */
export function dealFacts(d: WorkbenchDeal): Array<[string, string]> {
  return (
    [
      ['收费方式', d.fee],
      ['风险比例', d.riskRate != null ? d.riskRate + '%' : ''],
      ['指定日期', fmtCNDate(d.specified)],
      ['签订日期', fmtCNDate(d.from)],
      ['到期日期', d.to ? fmtCNDate(d.to) + (relDue(d.daysLeft) ? '（' + relDue(d.daysLeft) + '）' : '') : ''],
      ['代理阶段', d.stages.join(' · ')],
      ['归档状态', d.isFiled ? '已归档' : d.statusLabel],
      ['建档编号', d.filingNo],
      ['OA 编号', d.no],
    ] as Array<[string, string]>
  ).filter(([, v]) => !!v)
}

/** 收款记录行：合同收款 + 客户付款记录（各自保持时间顺序，日期年月日） */
export function dealPayRows(d: WorkbenchDeal): Array<{ when: string; money: string; note: string }> {
  return [
    ...d.payments.map((p) => ({
      when: fmtCNDate(p.received_at),
      money: fmtMoney(p.amount) ?? '¥0',
      note: (p.invoice_status_label || '') + (p.note ? ' · ' + p.note : ''),
    })),
    ...d.payRecords.map((p) => ({
      when: fmtCNDate(p.created_at),
      money: fmtMoney(p.amount) ?? '¥0',
      note: '客户付款记录' + (p.note ? ' · ' + p.note : ''),
    })),
  ]
}

/** 案件按阶段聚合（保持案件 id 升序的阶段顺序）：同阶段计数 ×N + 是否有在办 */
export function aggregateStages(cases: DealCase[]): Array<{ stage: string; n: number; live: boolean }> {
  const stages: Array<{ stage: string; n: number; live: boolean }> = []
  for (const c of [...cases].sort((a, b) => a.id - b.id)) {
    const last = stages[stages.length - 1]
    if (last && last.stage === c.proc) {
      last.n++
      last.live = last.live || !c.done
    } else {
      stages.push({ stage: c.proc, n: 1, live: !c.done })
    }
  }
  return stages
}

/* 复制动作（clipboard 优先，execCommand 兜底）已上提 @/lib/clipboard 的
 * copyText（workbench 抽屉 / home 工具卡 ≥2 feature 共用）。 */
