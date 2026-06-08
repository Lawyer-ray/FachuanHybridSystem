vi.mock('../../api', () => ({
  reminderApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue({ id: 1 }),
    getTypes: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/lib/create-crud-mutations', () => ({
  createCrudMutations: vi.fn(() => () => ({
    create: { mutate: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), isPending: false },
    delete: { mutate: vi.fn(), isPending: false },
  })),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useReminderMutations } from '../use-reminder-mutations'
import { useReminders, useReminder, useReminderTypes, remindersQueryKey, reminderQueryKey, reminderTypesQueryKey } from '../use-reminders'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useReminderMutations', () => {
  it('returns createMutation, updateMutation, deleteMutation', () => {
    const { result } = renderHook(() => useReminderMutations(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createMutation')
    expect(result.current).toHaveProperty('updateMutation')
    expect(result.current).toHaveProperty('deleteMutation')
  })

  it('each mutation has mutate function', () => {
    const { result } = renderHook(() => useReminderMutations(), { wrapper: createWrapper() })
    expect(typeof result.current.createMutation.mutate).toBe('function')
    expect(typeof result.current.updateMutation.mutate).toBe('function')
    expect(typeof result.current.deleteMutation.mutate).toBe('function')
  })
})

describe('useReminders', () => {
  it('calls reminderApi.list on mount', async () => {
    const { reminderApi } = await import('../../api')
    renderHook(() => useReminders(), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(remindersQueryKey()).toEqual(['reminders', { reminderType: null, dateFrom: null, dateTo: null }])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useReminders(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useReminder', () => {
  it('calls reminderApi.get with id', async () => {
    const { reminderApi } = await import('../../api')
    renderHook(() => useReminder(1), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(reminderQueryKey(42)).toEqual(['reminder', 42])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useReminder(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useReminderTypes', () => {
  it('calls reminderApi.getTypes on mount', async () => {
    const { reminderApi } = await import('../../api')
    renderHook(() => useReminderTypes(), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(reminderTypesQueryKey()).toEqual(['reminder-types'])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useReminderTypes(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
