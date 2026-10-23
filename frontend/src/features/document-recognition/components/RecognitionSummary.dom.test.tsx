// @vitest-environment jsdom
/**
 * RecognitionSummary 测试（jsdom）。
 *
 * 识别结果摘要卡的分支全部集中在「有值才渲染」：
 * - 文书类型标签（已知类型带配色 / 未知回落「文书」）
 * - 案号、置信度、模型与提取方法（未知方法回落原值）
 * - 降级识别徽章
 * - 文书链接（走 safeHttpUrl 白名单）
 * - 联系人/地址块（两者独立显隐，全空时整块不渲染）
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../constants', () => ({
  DOC_TYPE_LABELS: { summons: '传票', execution: '执行文书' },
  EXTRACTION_METHOD_LABELS: { ocr: 'OCR 识别' },
}))
vi.mock('../domain', () => ({ formatContacts: (c: unknown[]) => (c.length ? c.join('、') : '') }))

import { RecognitionSummary } from './RecognitionSummary'

function makeTask(over: Record<string, unknown> = {}) {
  return { file_url: '/media/a.pdf', contacts: [], address: '', ...over } as never
}

function makeRec(over: Record<string, unknown> = {}) {
  return {
    document_type: 'summons',
    case_number: null,
    confidence: null,
    llm_model: null,
    extraction_method: null,
    degraded: false,
    ...over,
  } as never
}

function renderCard(taskOver: Record<string, unknown> = {}, recOver: Record<string, unknown> = {}) {
  const utils = render(
    <RecognitionSummary task={makeTask(taskOver)} recognition={makeRec(recOver)} previewUrl="/media/a.pdf?ticket=t" />,
  )
  return utils
}

describe('RecognitionSummary：类型标签', () => {
  it('已知类型显示对应中文并带配色', () => {
    const { container } = renderCard({}, { document_type: 'summons' })
    const badge = screen.getByText('传票')
    expect(badge.className).toContain('status-blue')
    container.remove()
  })

  it('未知类型回落「文书」且用默认边框', () => {
    const { container } = renderCard({}, { document_type: 'unknown_type' })
    const badge = screen.getByText('文书')
    expect(badge.className).toContain('border-border')
    container.remove()
  })

  it('document_type 为 null 时同样回落「文书」', () => {
    const { container } = renderCard({}, { document_type: null })
    expect(screen.getByText('文书')).toBeTruthy()
    container.remove()
  })
})

describe('RecognitionSummary：可选字段', () => {
  it('有案号时渲染', () => {
    const { container } = renderCard({}, { case_number: '（20XX）京01民初1号' })
    expect(screen.getByText('（20XX）京01民初1号')).toBeTruthy()
    container.remove()
  })

  it('无案号时不渲染', () => {
    const { container } = renderCard({}, { case_number: null })
    expect(screen.queryByText(/京01民初/)).toBeNull()
    container.remove()
  })

  it('置信度四舍五入为百分比', () => {
    const { container } = renderCard({}, { confidence: 0.876 })
    expect(screen.getByText(/置信度 88%/)).toBeTruthy()
    container.remove()
  })

  it('无置信度时不渲染', () => {
    const { container } = renderCard({}, { confidence: null })
    expect(screen.queryByText(/置信度/)).toBeNull()
    container.remove()
  })

  it('有 llm_model 与已知方法时显示「模型 · 方法」', () => {
    const { container } = renderCard({}, { llm_model: 'qwen-max', extraction_method: 'ocr' })
    expect(screen.getByText(/qwen-max · OCR 识别/)).toBeTruthy()
    container.remove()
  })

  it('无 llm_model 时回落「关键词+规则」', () => {
    const { container } = renderCard({}, { llm_model: null })
    expect(screen.getByText(/关键词\+规则/)).toBeTruthy()
    container.remove()
  })

  it('未知提取方法回落原值', () => {
    const { container } = renderCard({}, { llm_model: 'm', extraction_method: 'custom_method' })
    expect(screen.getByText(/· custom_method/)).toBeTruthy()
    container.remove()
  })

  it('degraded 时显示降级徽章', () => {
    const { container } = renderCard({}, { degraded: true })
    expect(screen.getByText(/降级识别·建议核对/)).toBeTruthy()
    container.remove()
  })

  it('未降级时不显示降级徽章', () => {
    const { container } = renderCard({}, { degraded: false })
    expect(screen.queryByText(/降级识别/)).toBeNull()
    container.remove()
  })
})

describe('RecognitionSummary：文书链接', () => {
  it('有 previewUrl 时渲染「查看文书」链接并过 safeHttpUrl', () => {
    const { container } = renderCard()
    const link = screen.getByRole('link', { name: /查看文书/ })
    expect(link.getAttribute('href')).toContain('/media/a.pdf')
    expect(link.getAttribute('rel')).toContain('noopener')
    container.remove()
  })

  it('previewUrl 为空串时不渲染链接', () => {
    const utils = render(
      <RecognitionSummary task={makeTask()} recognition={makeRec()} previewUrl="" />,
    )
    expect(screen.queryByRole('link', { name: /查看文书/ })).toBeNull()
    utils.unmount()
  })

  it('previewUrl 为 javascript: 时被白名单挡下', () => {
    const utils = render(
      <RecognitionSummary task={makeTask()} recognition={makeRec()} previewUrl="javascript:alert(1)" />,
    )
    const link = screen.queryByRole('link', { name: /查看文书/ })
    if (link) expect(link.getAttribute('href') ?? '').not.toContain('javascript:')
    utils.unmount()
  })
})

describe('RecognitionSummary：联系人/地址块', () => {
  it('有联系人时渲染', () => {
    const { container } = renderCard({ contacts: ['张三', '李四'] })
    expect(container.textContent).toContain('张三、李四')
    container.remove()
  })

  it('有地址时渲染', () => {
    const { container } = renderCard({ address: '北京市朝阳区某路' })
    expect(container.textContent).toContain('北京市朝阳区某路')
    container.remove()
  })

  it('两者都有时同一块内各占一行', () => {
    const { container } = renderCard({ contacts: ['张三'], address: '某地址' })
    expect(container.textContent).toContain('张三')
    expect(container.textContent).toContain('某地址')
    container.remove()
  })

  it('两者都空时整块不渲染', () => {
    const { container } = renderCard({ contacts: [], address: '' })
    // 没有 UserRound/MapPin 图标即代表整块未渲染
    expect(container.querySelectorAll('svg').length).toBeLessThanOrEqual(2) // 仅 ExternalLink + TriangleAlert 位
    container.remove()
  })

  it('contacts 为 null 时不崩', () => {
    const { container } = renderCard({ contacts: null, address: '地址' })
    expect(container.textContent).toContain('地址')
    container.remove()
  })
})
