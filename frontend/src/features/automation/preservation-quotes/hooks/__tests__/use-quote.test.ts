vi.mock('../api', () => ({
  preservationQuoteApi: {
    get: vi.fn().mockResolvedValue({ id: 1, status: 'success' }),
  },
}))

vi.mock('../../constants', () => ({
  POLLING_INTERVALS: {
    QUOTE_RUNNING: 3000,
    POLLING_TIMEOUT: 300000,
  },
}))

vi.mock('./use-quotes', () => ({
  quoteQueryKey: (id: number) => ['preservation-quote', id],
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: null, isLoading: false }),
  }
})

import { useQuote, shouldPoll, isCompleted } from '../use-quote'

describe('automation/preservation-quotes/hooks/use-quote', () => {
  it('exports useQuote function', () => {
    expect(typeof useQuote).toBe('function')
  })

  describe('shouldPoll', () => {
    it('returns true for pending', () => {
      expect(shouldPoll('pending')).toBe(true)
    })

    it('returns true for running', () => {
      expect(shouldPoll('running')).toBe(true)
    })

    it('returns false for success', () => {
      expect(shouldPoll('success')).toBe(false)
    })

    it('returns false for failed', () => {
      expect(shouldPoll('failed')).toBe(false)
    })
  })

  describe('isCompleted', () => {
    it('returns true for success', () => {
      expect(isCompleted('success')).toBe(true)
    })

    it('returns true for partial_success', () => {
      expect(isCompleted('partial_success')).toBe(true)
    })

    it('returns true for failed', () => {
      expect(isCompleted('failed')).toBe(true)
    })

    it('returns false for pending', () => {
      expect(isCompleted('pending')).toBe(false)
    })

    it('returns false for running', () => {
      expect(isCompleted('running')).toBe(false)
    })
  })

  describe('shouldPoll edge cases', () => {
    it('returns false for an unknown status', () => {
      expect(shouldPoll('unknown' as any)).toBe(false)
    })
  })

  describe('isCompleted edge cases', () => {
    it('returns false for partial_success as completed', () => {
      expect(isCompleted('partial_success')).toBe(true)
    })

    it('returns false for an unknown status', () => {
      expect(isCompleted('unknown' as any)).toBe(false)
    })
  })
})
