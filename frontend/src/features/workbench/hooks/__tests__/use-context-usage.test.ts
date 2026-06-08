vi.mock('../../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector: Function) => selector({
    messages: [
      { content: 'Hello', metadata: {} },
      { content: '你好世界', metadata: {} },
    ],
    models: [{ id: 'gpt-4', context_window: 8000 }],
    selectedModel: 'gpt-4',
  })),
}))

import { renderHook } from '@testing-library/react'
import { estimateTokens, estimateMessagesTokens, formatTokens, useContextUsage } from '../use-context-usage'

describe('estimateTokens', () => {
  it('returns 0 for empty string', () => {
    expect(estimateTokens('')).toBe(0)
  })

  it('returns at least 1 for non-empty text', () => {
    expect(estimateTokens('a')).toBeGreaterThanOrEqual(1)
  })

  it('counts Chinese characters with higher weight', () => {
    const chineseTokens = estimateTokens('中')
    const englishTokens = estimateTokens('a')
    expect(chineseTokens).toBeGreaterThan(englishTokens)
  })
})

describe('estimateMessagesTokens', () => {
  it('returns 0 for empty messages array', () => {
    expect(estimateMessagesTokens([])).toBe(0)
  })

  it('sums tokens from all messages', () => {
    const messages = [
      { content: 'hello' } as any,
      { content: 'world' } as any,
    ]
    expect(estimateMessagesTokens(messages)).toBeGreaterThan(0)
  })

  it('handles messages with no content', () => {
    const messages = [{ content: '' } as any]
    expect(estimateMessagesTokens(messages)).toBe(0)
  })
})

describe('formatTokens', () => {
  it('returns string for numbers under 1000', () => {
    expect(formatTokens(500)).toBe('500')
  })

  it('formats numbers >= 1000 with K suffix', () => {
    expect(formatTokens(1500)).toBe('1.5K')
  })

  it('handles zero', () => {
    expect(formatTokens(0)).toBe('0')
  })
})

describe('useContextUsage', () => {
  it('returns percent, usedTokens, contextWindow, messageCount', () => {
    const { result } = renderHook(() => useContextUsage())
    expect(result.current).toHaveProperty('percent')
    expect(result.current).toHaveProperty('usedTokens')
    expect(result.current).toHaveProperty('contextWindow')
    expect(result.current).toHaveProperty('messageCount')
  })

  it('returns non-negative usedTokens', () => {
    const { result } = renderHook(() => useContextUsage())
    expect(result.current.usedTokens).toBeGreaterThanOrEqual(0)
  })

  it('returns contextWindow from model', () => {
    const { result } = renderHook(() => useContextUsage())
    expect(result.current.contextWindow).toBe(8000)
  })
})
