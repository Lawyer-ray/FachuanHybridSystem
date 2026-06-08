vi.mock('../api', () => ({
  reminderApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('../hooks/use-reminders', () => ({
  reminderQueryKey: (id: number) => ['reminder', id],
}))

vi.mock('@/lib/create-crud-mutations', () => ({
  createCrudMutations: vi.fn(() => () => ({
    create: { mutate: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), isPending: false },
    delete: { mutate: vi.fn(), isPending: false },
  })),
}))

import { useReminderMutations } from '../use-reminder-mutations'

describe('reminders/hooks/use-reminder-mutations', () => {
  it('exports useReminderMutations function', () => {
    expect(typeof useReminderMutations).toBe('function')
  })

  it('returns create, update, and delete mutations', () => {
    const result = useReminderMutations()
    expect(result).toHaveProperty('createMutation')
    expect(result).toHaveProperty('updateMutation')
    expect(result).toHaveProperty('deleteMutation')
  })

  it('each mutation has mutate method', () => {
    const result = useReminderMutations()
    expect(typeof result.createMutation.mutate).toBe('function')
    expect(typeof result.updateMutation.mutate).toBe('function')
    expect(typeof result.deleteMutation.mutate).toBe('function')
  })
})
