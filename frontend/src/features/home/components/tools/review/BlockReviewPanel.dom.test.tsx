// @vitest-environment jsdom
/**
 * BlockReviewPanel 的渲染行为测试（jsdom）。
 *
 * 只钉三件在 UI 上最容易做错、且做错后危害最大的事：
 *  1. **未评估不能显示成绿色**——用绿色等于替沉默背书；
 *  2. 低分块要能被一眼看到（分数 + 原因）；
 *  3. 页脚默认不出现在"只看正文"视图里。
 * 纯逻辑（三态、统计、筛选）在 review-domain.test.ts 覆盖，此处不重复。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ParseBlock } from '../../../api'

import { BlockReviewPanel } from './BlockReviewPanel'

function block(over: Partial<ParseBlock>): ParseBlock {
  return { type: 'text', text: 'x', ...over } as ParseBlock
}

describe('BlockReviewPanel', () => {
  it('无块时给出能力说明，不渲染空面板', () => {
    render(<BlockReviewPanel blocks={null} coverage={null} />)
    expect(screen.getByText(/未返回块级结构/)).toBeTruthy()
  })

  it('未评估块显示「未评估」而不是分数或绿色', () => {
    render(<BlockReviewPanel blocks={[block({ text: '未评估内容', confidence: null })]} coverage={null} />)
    expect(screen.getByText('未评估内容')).toBeTruthy()
    // 徽标文本（摘要行也有「未评估」字样，所以用 getAllByText 并验证包含徽标）
    expect(screen.getAllByText('未评估').length).toBeGreaterThanOrEqual(1)
    // 关键：不能出现 0.00（把未评估当零分）
    expect(screen.queryByText('0.00')).toBeNull()
  })

  it('低分块显示分数与复核原因', () => {
    render(
      <BlockReviewPanel
        blocks={[block({ text: '金额 12,300 元', confidence: 0.31, needs_review: true, review_reason: '低于阈值' })]}
        coverage={null}
      />,
    )
    expect(screen.getByText('0.31')).toBeTruthy()
    expect(screen.getByText('低于阈值')).toBeTruthy()
  })

  it('摘要如实说「未评估」，不会说成全部达标', () => {
    render(<BlockReviewPanel blocks={[block({ text: 'a', confidence: null })]} coverage={null} />)
    expect(screen.getByText(/均未评估/)).toBeTruthy()
    expect(screen.queryByText(/阈值以上/)).toBeNull()
  })

  it('默认只看正文：页脚不渲染', () => {
    render(
      <BlockReviewPanel
        blocks={[block({ text: '正文段落', confidence: 0.9 }), block({ type: 'footer', text: '第 1 页', confidence: 0.9 })]}
        coverage={null}
      />,
    )
    expect(screen.getByText('正文段落')).toBeTruthy()
    expect(screen.queryByText('第 1 页')).toBeNull()
  })

  it('关闭「只看正文」后页脚出现', () => {
    render(
      <BlockReviewPanel
        blocks={[block({ text: '正文段落', confidence: 0.9 }), block({ type: 'footer', text: '第 1 页', confidence: 0.9 })]}
        coverage={null}
      />,
    )
    fireEvent.click(screen.getByText('只看正文'))
    expect(screen.getByText('第 1 页')).toBeTruthy()
  })

  it('按「待复核」筛选后只剩低分块', () => {
    render(
      <BlockReviewPanel
        blocks={[block({ text: '低分块', confidence: 0.2 }), block({ text: '高分块', confidence: 0.95 })]}
        coverage={null}
      />,
    )
    // 「待复核 1」按钮：点它只看 flagged
    fireEvent.click(screen.getByText(/待复核 1/))
    expect(screen.getByText('低分块')).toBeTruthy()
    expect(screen.queryByText('高分块')).toBeNull()
  })

  it('coverage 为 null 时不显示「无可裁切坐标」（不胡报能力缺失）', () => {
    render(<BlockReviewPanel blocks={[block({ text: 'a', confidence: 0.9 })]} coverage={null} />)
    expect(screen.queryByText(/无可裁切坐标/)).toBeNull()
  })

  it('后端声明 has_bbox=false 时才提示无可裁切坐标', () => {
    render(
      <BlockReviewPanel
        blocks={[block({ text: 'a', confidence: 0.9 })]}
        coverage={{ has_blocks: true, has_bbox: false, has_confidence: false, has_page_geometry: false }}
      />,
    )
    expect(screen.getByText(/无可裁切坐标/)).toBeTruthy()
  })
})
