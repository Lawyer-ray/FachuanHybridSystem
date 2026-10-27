import { describe, expect, it } from 'vitest'

import type { WorkbenchDeal } from '../../../types'
import { crumbName, headerMetaParts } from './header-domain'

function makeDeal(over: Partial<WorkbenchDeal> = {}): WorkbenchDeal {
  return {
    id: 7,
    lit: true,
    caseType: 'civil',
    client: '某银行与某公司金融借款合同纠纷诉讼委托合同',
    ctype: '民商事',
    no: '',
    amount: '¥50,000',
    amountNum: 50000,
    fee: '半风险',
    from: '',
    to: '',
    daysLeft: null,
    status: 'active',
    statusLabel: '在办',
    specified: '',
    isFiled: true,
    filingNo: '2025_MS_HT_0031',
    oaUrl: '',
    customTerms: '',
    parties: { client: '某银行', other: '某公司' },
    partiesAll: [
      { name: '某银行', role: '委托人', idno: '', legalRep: '', phone: '', address: '', ours: true },
      { name: '某公司', role: '对方当事人', idno: '', legalRep: '', phone: '', address: '', ours: false },
      { name: '某五金', role: '对方当事人', idno: '', legalRep: '', phone: '', address: '', ours: false },
    ],
    team: [],
    primaryPhone: '',
    caseCount: 2,
    work: [],
    riskRate: 8,
    stages: [],
    primary: '黄崧',
    lawFirm: '',
    totalReceived: '¥50,000',
    totalInvoiced: null,
    unpaid: null,
    payments: [],
    payRecords: [],
    supps: [],
    ...over,
  }
}

describe('页头', () => {
  it('headerMetaParts：类型/状态加粗，建档尾随；我方→对方与主办不再出现在页头（右栏卡已展示）', () => {
    expect(headerMetaParts(makeDeal())).toEqual([
      { v: '民商事', strong: true },
      { v: '在办', strong: true },
      { k: '建档', v: '2025_MS_HT_0031' },
    ])
  })

  it('headerMetaParts：没有建档号只剩类型与状态', () => {
    const parts = headerMetaParts(makeDeal({ partiesAll: [], filingNo: '', primary: '' }))
    expect(parts).toEqual([{ v: '民商事', strong: true }, { v: '在办', strong: true }])
  })

  it('crumbName：超 18 字截断加省略号，短名原样', () => {
    expect(crumbName('短短的名字')).toBe('短短的名字')
    const long = '某市公路工程质量检测有限责任公司诉广东某交通投资有限公司及第三人某混凝土公司执行异议之诉一案'
    expect(crumbName(long)).toBe('某市公路工程质量检测有限责任公司诉广…')
    expect(crumbName(long).length).toBe(19)
  })
})
