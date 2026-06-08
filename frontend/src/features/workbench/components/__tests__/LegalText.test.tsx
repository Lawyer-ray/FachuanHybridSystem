/**
 * LegalText Component Tests
 * 测试法律文本高亮渲染组件
 */

import { render, screen } from '@testing-library/react'
import { LegalText } from '../LegalText'

describe('LegalText', () => {
  it('renders plain text without legal references', () => {
    render(<LegalText text="This is plain text" />)
    expect(screen.getByText('This is plain text')).toBeInTheDocument()
  })

  it('renders empty string', () => {
    const { container } = render(<LegalText text="" />)
    expect(container.textContent).toBe('')
  })

  it('renders text with case number highlighted', () => {
    const text = '依据（2024）京0101民初12345号判决书'
    render(<LegalText text={text} />)
    // Case number should be rendered in a highlighted span
    expect(screen.getByText(/（2024）京0101民初12345号/)).toBeInTheDocument()
  })

  it('renders text with law article highlighted', () => {
    const text = '根据《民法典》第一百二十三条的规定'
    render(<LegalText text={text} />)
    expect(screen.getByText(/《民法典》第一百二十三条/)).toBeInTheDocument()
  })

  it('renders text with money reference highlighted', () => {
    const text = '赔偿人民币100000元'
    render(<LegalText text={text} />)
    expect(screen.getByText(/人民币100000元/)).toBeInTheDocument()
  })

  it('preserves surrounding text around legal references', () => {
    const text = '根据《民法典》第一条，原告要求赔偿人民币50000元'
    render(<LegalText text={text} />)
    expect(screen.getByText(/根据/)).toBeInTheDocument()
    expect(screen.getByText(/，原告要求赔偿/)).toBeInTheDocument()
  })
})
