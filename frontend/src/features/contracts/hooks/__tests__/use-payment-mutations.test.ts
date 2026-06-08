vi.mock('../api', () => ({
  paymentsApi: {
    create: vi.fn().mockResolvedValue({}),
    update: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
    useQueryClient: vi.fn().mockReturnValue({ invalidateQueries: vi.fn() }),
  }
})

import { usePaymentMutations } from '../use-payment-mutations'

describe('contracts/hooks/use-payment-mutations', () => {
  it('exports usePaymentMutations function', () => {
    expect(typeof usePaymentMutations).toBe('function')
  })

  it('returns mutation functions', () => {
    const result = usePaymentMutations(1)
    expect(result).toHaveProperty('createPayment')
    expect(result).toHaveProperty('updatePayment')
    expect(result).toHaveProperty('deletePayment')
  })

  it('createPayment has mutate function', () => {
    const result = usePaymentMutations(1)
    expect(typeof result.createPayment.mutate).toBe('function')
  })
})
