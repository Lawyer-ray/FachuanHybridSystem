vi.mock('../api', () => ({
  paymentsApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn().mockResolvedValue({}),
    update: vi.fn().mockResolvedValue({}),
    remove: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: [], isLoading: false }),
    useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
    useQueryClient: vi.fn().mockReturnValue({ invalidateQueries: vi.fn() }),
  }
})

import { usePayments } from '../use-payments'
import { usePaymentMutations } from '../use-payment-mutations'

describe('contracts/hooks/use-payments', () => {
  it('exports usePayments function', () => {
    expect(typeof usePayments).toBe('function')
  })

  it('returns data and isLoading', () => {
    const result = usePayments(1)
    expect(result).toHaveProperty('data')
    expect(result).toHaveProperty('isLoading')
  })
})

describe('contracts/hooks/use-payment-mutations', () => {
  it('exports usePaymentMutations function', () => {
    expect(typeof usePaymentMutations).toBe('function')
  })

  it('returns create and update mutations', () => {
    const result = usePaymentMutations()
    expect(result).toHaveProperty('createPayment')
    expect(result).toHaveProperty('updatePayment')
    expect(result).toHaveProperty('deletePayment')
  })
})
