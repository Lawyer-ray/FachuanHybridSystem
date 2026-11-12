import { describe, expect, it } from 'vitest'

import { formatAmount, RED_REENACT_COPY, RED_TONE } from './constants'
import {
  amountText,
  canConfirm,
  canConfirmRedReenact,
  hasUsableSuggestion,
  invoiceHeadline,
  invoiceSubtitle,
  isRed,
  pendingBadgeCount,
  redHeadline,
  splitByRedGroup,
} from './domain'
import type { InvoiceCandidate, InvoiceIntake, RedGroup } from './types'

function candidate(overrides: Partial<InvoiceCandidate> = {}): InvoiceCandidate {
  return {
    contract_id: 160,
    contract_name: '张某与某公司合同纠纷',
    kind: 'project_code',
    score: 1,
    reasons: ['备注栏项目号 2025GZM0001 命中'], // privacy-allow 虚构样例，非真实项目号
    caveat: '',
    ...overrides,
  }
}

function intake(overrides: Partial<InvoiceIntake> = {}): InvoiceIntake {
  return {
    id: 1,
    invoice_number: '26442000012915552076',
    invoice_date: '2026-11-04',
    total_amount: '2400.00',
    buyer_name: '张三',
    project_code: '2025GZM0001', // privacy-allow 虚构样例，非真实项目号
    remark: '2025GZM0001-张某与某公司合同纠纷', // privacy-allow 虚构样例，非真实项目号
    status: 'pending',
    status_label: '待确认',
    suggested_contract_id: 160,
    suggested_contract_name: '张某与某公司合同纠纷',
    suggested_payment_id: null,
    payment_pick_confidence: 'no_payment',
    payment_pick_note: '',
    payment_options: [],
    confirmed_contract_id: null,
    confirmed_contract_name: null,
    confirmed_payment_id: null,
    invoice_id: null,
    invoice_display_filename: '',
    invoice_folder_subpath: '',
    candidates: [candidate()],
    excluded_hints: [],
    inbox_message_id: 10,
    subject: '',
    sender: '',
    is_red: false,
    red_against_number: '',
    red_confirmation_no: '',
    offset_invoice: null,
    supersedes_intake_id: null,
    superseded_by_intake_id: null,
    reatch_group: null,
    ...overrides,
  }
}

describe('invoiceHeadline', () => {
  // 结论文案**不带 ✓ 字符**：行组件已用 Check 图标表达"匹配成功"，
  // 文本再来一个就成了「✓ ✓」（实测出现过）。图标与文案各管一件事。
  it('有建议时给出信号标签 + 项目名（不含 ✓，图标由调用方给）', () => {
    expect(invoiceHeadline(intake())).toBe('确定性匹配：张某与某公司合同纠纷')
    expect(invoiceHeadline(intake())).not.toContain('✓')
  })

  it('按最高信号等级取标签：同时有项目号与当事人匹配时用项目号', () => {
    const row = intake({
      candidates: [
        candidate({ contract_id: 9, kind: 'party_name', contract_name: '别的项目' }),
        candidate({ kind: 'case_text' }),
        candidate({ kind: 'project_code' }),
      ],
    })
    expect(invoiceHeadline(row)).toBe('确定性匹配：张某与某公司合同纠纷')
  })

  it('只有案由匹配时用案由标签', () => {
    const row = intake({ candidates: [candidate({ kind: 'case_text' })] })
    expect(invoiceHeadline(row)).toContain('案由匹配')
  })

  it('只有当事人匹配时用当事人标签', () => {
    const row = intake({ candidates: [candidate({ kind: 'party_name' })] })
    expect(invoiceHeadline(row)).toContain('当事人匹配')
  })

  it('有建议但无候选时退回「系统建议」，不空标签', () => {
    const row = intake({ candidates: [] })
    expect(invoiceHeadline(row)).toBe('系统建议：张某与某公司合同纠纷')
  })

  it('无建议时明说要人工选择', () => {
    const row = intake({ suggested_contract_id: null, suggested_contract_name: null, candidates: [] })
    expect(invoiceHeadline(row)).toBe('无可匹配的在办项目，需人工选择')
  })
})

describe('hasUsableSuggestion', () => {
  it('有建议 → true', () => {
    expect(hasUsableSuggestion(intake())).toBe(true)
  })

  it('无建议 → false', () => {
    expect(hasUsableSuggestion(intake({ suggested_contract_id: null }))).toBe(false)
  })

  it('只认 id，不看合同名是否为空', () => {
    expect(hasUsableSuggestion(intake({ suggested_contract_name: null }))).toBe(true)
  })
})

describe('canConfirm', () => {
  it('待确认 + 有建议 → true', () => {
    expect(canConfirm(intake())).toBe(true)
  })

  it('无建议 → false', () => {
    expect(canConfirm(intake({ suggested_contract_id: null }))).toBe(false)
  })

  it('已绑定的不再可确认 → false', () => {
    expect(canConfirm(intake({ status: 'confirmed' }))).toBe(false)
  })
})

describe('invoiceSubtitle', () => {
  it('购买方 · 去掉项目号后的案由片段', () => {
    expect(invoiceSubtitle(intake())).toBe('张三 · 张某与某公司合同纠纷')
  })

  it('案由超 30 字截断加省略号', () => {
    const remark = `2025GZM0001-${'长'.repeat(40)}` // privacy-allow 虚构样例，非真实项目号
    const text = invoiceSubtitle(intake({ remark }))
    expect(text).toContain('…')
    expect(text.length).toBeLessThan(40)
  })

  it('无案由时只剩购买方，不留悬空分隔符', () => {
    expect(invoiceSubtitle(intake({ remark: '', project_code: '' }))).toBe('张三')
  })

  it('无购买方时只剩案由', () => {
    expect(invoiceSubtitle(intake({ buyer_name: '' }))).toBe('张某与某公司合同纠纷')
  })
})

describe('amountText', () => {
  it('金额加币种与千分位', () => {
    expect(amountText(intake())).toBe('¥2,400.00')
  })

  it('识别失败（null）给占位而不是孤零零的 ¥', () => {
    expect(amountText(intake({ total_amount: null }))).toBe('金额未识别')
  })

  it('空串同样给占位', () => {
    expect(amountText(intake({ total_amount: '' }))).toBe('金额未识别')
  })
})

// ── 红字发票 ──────────────────────────────────────────

/** 组内成员（契约 GroupItemOut） */
function item(over: Partial<RedGroup['red']> = {}) {
  return { intake_id: 2, invoice_id: null, invoice_number: '264420000102001', total_amount: '-40000.00', ...over }
}

function group(over: Partial<RedGroup> = {}): RedGroup {
  return {
    group_key: 'g-1',
    original: item({ intake_id: null, invoice_id: 88, invoice_number: '264420000368336', total_amount: '40000.00' }),
    red: item(),
    reissue: item({ intake_id: 3, invoice_number: '264420000185941', total_amount: '40000.00' }),
    ...over,
  }
}

/** 红票 intake：票面事实（被冲票号 + 负数金额）与 offset 原票 */
function redIntake(over: Partial<InvoiceIntake> = {}): InvoiceIntake {
  return intake({
    id: 2,
    invoice_number: '264420000102001',
    total_amount: '-40000.00',
    red_against_number: '264420000368336',
    is_red: true,
    offset_invoice: {
      id: 88,
      invoice_number: '264420000368336',
      total_amount: '40000.00',
      contract_id: 160,
      contract_name: '陈某非诉专项（关厂、清盘）',
      folder_subpath: '合同/ invoices',
    },
    ...over,
  })
}

describe('isRed', () => {
  it('有被冲票号 → 红票（即使金额为正，识别层也可能没取到负号）', () => {
    expect(isRed(intake({ red_against_number: '264420000368336', total_amount: '40000.00' }))).toBe(true)
  })

  it('金额为负 → 红票（即使没识别出原票号）', () => {
    expect(isRed(intake({ red_against_number: '', total_amount: '-2400.00' }))).toBe(true)
  })

  it('普通蓝票 → 不是红票', () => {
    expect(isRed(intake())).toBe(false)
  })

  it('不依赖后端算好的 is_red：字段缺省时仍按票面事实判', () => {
    expect(isRed(intake({ is_red: false, total_amount: '-1.00' }))).toBe(true)
  })
})

describe('redHeadline', () => {
  it('原票在库：冲销 + 尾 6 位票号 + 原票金额', () => {
    expect(redHeadline(redIntake())).toBe('冲销 …368336（¥40,000.00）')
    expect(redHeadline(redIntake({ id: 4, invoice_number: '…add', offset_invoice: { ...redIntake().offset_invoice!, total_amount: '40000.00', folder_subpath: '合同/已冲红' } }))).toBe('冲销 …368336（¥40,000.00）')
  })

  it('原票不在库：明说需人工，而不是留空占位', () => {
    expect(redHeadline(redIntake({ offset_invoice: null }))).toBe('冲销 …368336（原票不在系统里）')
  })

  it('原票在库但金额未识别：给出明确的未识别占位', () => {
    const row = redIntake({ offset_invoice: { ...redIntake().offset_invoice!, total_amount: null, folder_subpath: '' } })
    expect(redHeadline(row)).toBe('冲销 …368336（金额未识别）')
  })
})

describe('amountText 三态（红票）', () => {
  it('红票 + 金额未识别 → 「红票金额未识别」（不是笼统的「金额未识别」）', () => {
    expect(amountText(redIntake({ total_amount: null }))).toBe('红票金额未识别')
  })

  it('红票 + 有金额 → 保留负号', () => {
    expect(amountText(redIntake())).toBe('¥-40,000.00')
  })

  it('非红票 + 金额未识别 → 「金额未识别」', () => {
    expect(amountText(intake({ total_amount: null }))).toBe('金额未识别')
  })
})

describe('canConfirm 的红票闸门（D5）', () => {
  it('红票即使有系统建议也不能一键确认', () => {
    expect(canConfirm(redIntake())).toBe(false)
  })

  it('普通票不受影响', () => {
    expect(canConfirm(intake())).toBe(true)
  })
})

describe('canConfirmRedReenact', () => {
  it('红票 + 原票在库 + 金额已识别 + 有新票 → true', () => {
    expect(canConfirmRedReenact(group())).toBe(true)
  })

  it('原票不在库 → false（无论红票自己的 offset_invoice 有没有值）', () => {
    expect(canConfirmRedReenact(group({ original: null }))).toBe(false)
  })

  it('红票金额未识别 → false（否则 Sum 里少一笔负数，账直接错）', () => {
    expect(canConfirmRedReenact(group({ red: item({ total_amount: null }) }))).toBe(false)
    expect(canConfirmRedReenact(group({ red: item({ total_amount: '' }) }))).toBe(false)
  })

  it('没有重开的新票 → false（那是「仅冲红」）', () => {
    expect(canConfirmRedReenact(group({ reissue: null }))).toBe(false)
  })

  it('新票金额未识别 → false', () => {
    expect(canConfirmRedReenact(group({ reissue: item({ total_amount: null }) }))).toBe(false)
  })

  it('group 为 null（不在任何组） → false', () => {
    expect(canConfirmRedReenact(null)).toBe(false)
  })
})

describe('splitByRedGroup', () => {
  const red = redIntake({ reatch_group: group() })
  const reissue = intake({
    id: 3,
    invoice_number: '264420000185941',
    invoice_date: '2026-11-11',
    reatch_group: group(),
  })
  const plain = intake({ id: 5 })

  it('同组的红票与新票聚成一组，红票在前、新票在后', () => {
    // 故意把新票放在前面：聚组后顺序必须被纠正
    const { groups, standalones } = splitByRedGroup([reissue, plain, red])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.groupKey).toBe('g-1')
    expect(groups[0]!.items.map((i) => i.id)).toEqual([2, 3])
    expect(standalones.map((i) => i.id)).toEqual([5])
  })

  it('保持组的首次出现顺序', () => {
    const a = redIntake({ id: 10, reatch_group: group({ group_key: 'a' }) })
    const b = redIntake({ id: 11, reatch_group: group({ group_key: 'b' }) })
    const { groups } = splitByRedGroup([b, a])
    expect(groups.map((g) => g.groupKey)).toEqual(['b', 'a'])
  })

  it('没有 reatch_group 的都是单行', () => {
    const { groups, standalones } = splitByRedGroup([plain])
    expect(groups).toEqual([])
    expect(standalones).toHaveLength(1)
  })

  it('空列表不炸', () => {
    expect(splitByRedGroup([])).toEqual({ groups: [], standalones: [] })
  })
})

describe('pendingBadgeCount', () => {
  it('单行条数 + 组数，不是原始 intake 条数', () => {
    const red = redIntake({ reatch_group: group() })
    const reissue = intake({ id: 3, reatch_group: group() })
    const plain = intake({ id: 5 })
    const { groups, standalones } = splitByRedGroup([red, reissue, plain])
    // 原始 3 条 → 用户眼里只有 2 件事
    expect(pendingBadgeCount(groups, standalones)).toBe(2)
  })

  it('全空 → 0', () => {
    expect(pendingBadgeCount([], [])).toBe(0)
  })
})

describe('红字发票常量', () => {
  it('RED_TONE 只用 destructive 语义令牌，不自创色值', () => {
    expect(RED_TONE.chip).toContain('destructive')
    expect(RED_TONE.chip).not.toMatch(/#[0-9a-f]/i)
    expect(RED_TONE.tone).toContain('destructive')
  })

  it('RED_REENACT_COPY 三档文案齐全', () => {
    expect(RED_REENACT_COPY.confirm).toBe('冲红并确认重开')
    expect(RED_REENACT_COPY.confirmOnly).toBe('仅冲红')
    expect(RED_REENACT_COPY.blocked).toContain('原票不在系统里')
  })
})

describe('formatAmount', () => {
  it('两位小数 + 千分位', () => {
    expect(formatAmount('10000.00')).toBe('¥10,000.00')
    expect(formatAmount('2400')).toBe('¥2,400.00')
    expect(formatAmount('0')).toBe('¥0.00')
  })

  it('小数按四舍五入保留两位', () => {
    expect(formatAmount('12.345')).toBe('¥12.35')
  })

  it('负数为退款票时保留符号', () => {
    expect(formatAmount('-2400')).toBe('¥-2,400.00')
  })

  it('非法值不炸，原样带币种', () => {
    expect(formatAmount('abc')).toBe('¥abc')
  })

  it('空串按 Number("")===0 输出 ¥0.00，不抛错', () => {
    // 记下这个边界：组件层用 amountText 把 null/'' 提前挡掉，formatAmount 自身不做空值判断
    expect(formatAmount('')).toBe('¥0.00')
  })
})
