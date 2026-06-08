vi.mock('../api', () => ({
  templateApi: {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue({ id: 1 }),
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/lib/create-crud-mutations', () => ({
  createCrudMutations: vi.fn(() => () => ({
    create: { mutate: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), isPending: false },
    delete: { mutate: vi.fn(), isPending: false },
  })),
}))

import { useTemplateMutations } from '../use-template-mutations'

describe('templates/hooks/use-template-mutations', () => {
  it('exports useTemplateMutations', () => {
    expect(useTemplateMutations).toBeDefined()
  })
})
