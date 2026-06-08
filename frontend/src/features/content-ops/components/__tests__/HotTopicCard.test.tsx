import { render, screen } from '@testing-library/react'
import { HotTopicCard } from '../HotTopicCard'

describe('HotTopicCard', () => {
  const baseTopic = {
    rank: 1,
    title: 'Test Hot Topic',
    heat: 50000,
    url: 'https://example.com',
    source: 'baidu',
  }

  it('renders topic title', () => {
    render(<HotTopicCard topic={baseTopic} />)
    expect(screen.getByText('Test Hot Topic')).toBeInTheDocument()
  })

  it('renders rank number', () => {
    render(<HotTopicCard topic={baseTopic} />)
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('renders source label', () => {
    render(<HotTopicCard topic={baseTopic} />)
    expect(screen.getByText('百度')).toBeInTheDocument()
  })

  it('renders formatted heat count', () => {
    render(<HotTopicCard topic={baseTopic} />)
    expect(screen.getByText('5.0万')).toBeInTheDocument()
  })

  it('renders translated title when provided', () => {
    render(<HotTopicCard topic={baseTopic} translatedTitle="Translated Title" />)
    expect(screen.getByText('Translated Title')).toBeInTheDocument()
    // Original title shown as subtitle
    expect(screen.getByText('Test Hot Topic')).toBeInTheDocument()
  })

  it('renders link with correct href', () => {
    render(<HotTopicCard topic={baseTopic} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', 'https://example.com')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('handles null heat', () => {
    const topic = { ...baseTopic, heat: null }
    const { container } = render(<HotTopicCard topic={topic} />)
    // Flame icon should not be visible when heat is null
    expect(container.querySelector('[class*="text-orange"]')).not.toBeInTheDocument()
  })

  it('handles small heat numbers', () => {
    const topic = { ...baseTopic, heat: 500 }
    render(<HotTopicCard topic={topic} />)
    expect(screen.getByText('500')).toBeInTheDocument()
  })

  it('renders raw source when not in label map', () => {
    const topic = { ...baseTopic, source: 'unknown_source' }
    render(<HotTopicCard topic={topic} />)
    expect(screen.getByText('unknown_source')).toBeInTheDocument()
  })
})
