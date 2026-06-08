vi.mock('../api', () => ({
  lawFirmApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('./use-lawfirm', () => ({
  lawFirmQueryKey: (id: number) => ['lawfirm', id],
}))

vi.mock('./use-lawfirms', () => ({
  lawFirmsQueryKey: ['lawfirms'],
}))

vi.mock('@/lib/create-crud-mutations', () => ({
  createCrudMutations: vi.fn(() => () => ({
    create: { mutate: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), isPending: false },
    delete: { mutate: vi.fn(), isPending: false },
  })),
}))

import { useLawFirmMutations } from '../use-lawfirm-mutations'

describe('organization/hooks/use-lawfirm-mutations', () => {
  it('exports useLawFirmMutations function', () => {
    expect(typeof useLawFirmMutations).toBe('function')
  })

  it('returns create, update, and delete mutations', () => {
    const result = useLawFirmMutations()
    expect(result).toHaveProperty('createLawFirm')
    expect(result).toHaveProperty('updateLawFirm')
    expect(result).toHaveProperty('deleteLawFirm')
  })
})
