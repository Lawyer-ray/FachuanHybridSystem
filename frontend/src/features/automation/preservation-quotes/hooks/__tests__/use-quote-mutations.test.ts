vi.mock('../api', () => ({
  preservationQuoteApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    execute: vi.fn().mockResolvedValue({ id: 1, status: 'running' }),
    retry: vi.fn().mockResolvedValue({ id: 1, status: 'running' }),
  },
}))

vi.mock('./use-quotes', () => ({
  quoteQueryKey: (id: number) => ['preservation-quote', id],
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
    useQueryClient: vi.fn().mockReturnValue({
      invalidateQueries: vi.fn(),
      setQueryData: vi.fn(),
    }),
  }
})

import { useCreateQuote, useExecuteQuote, useRetryQuote } from '../use-quote-mutations'

describe('automation/preservation-quotes/hooks/use-quote-mutations', () => {
  it('exports useCreateQuote function', () => {
    expect(typeof useCreateQuote).toBe('function')
  })

  it('exports useExecuteQuote function', () => {
    expect(typeof useExecuteQuote).toBe('function')
  })

  it('exports useRetryQuote function', () => {
    expect(typeof useRetryQuote).toBe('function')
  })
})
