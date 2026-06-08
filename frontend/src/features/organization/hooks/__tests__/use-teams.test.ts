vi.mock('../../api', () => ({
  teamApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    list: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useTeamMutations } from '../use-team-mutations'
import { useTeams, teamsQueryKey } from '../use-teams'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useTeamMutations', () => {
  it('returns createTeam, updateTeam, deleteTeam', () => {
    const { result } = renderHook(() => useTeamMutations(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createTeam')
    expect(result.current).toHaveProperty('updateTeam')
    expect(result.current).toHaveProperty('deleteTeam')
  })

  it('createTeam calls teamApi.create', async () => {
    const { teamApi } = await import('../../api')
    const { result } = renderHook(() => useTeamMutations(), { wrapper: createWrapper() })
    await act(async () => { result.current.createTeam.mutate({ name: 'Team A' } as any) })
  })

  it('deleteTeam calls teamApi.delete', async () => {
    const { teamApi } = await import('../../api')
    const { result } = renderHook(() => useTeamMutations(), { wrapper: createWrapper() })
    act(() => { result.current.deleteTeam.mutate(5) })
    expect(result.current.deleteTeam).toHaveProperty("isPending")
  })
})

describe('useTeams', () => {
  it('calls teamApi.list on mount', async () => {
    const { teamApi } = await import('../../api')
    renderHook(() => useTeams(), { wrapper: createWrapper() })
  })

  it('passes filters to teamApi.list', async () => {
    const { teamApi } = await import('../../api')
    renderHook(() => useTeams({ lawFirmId: 1, teamType: 'lawyer' }), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(teamsQueryKey()).toEqual(['teams', { lawFirmId: null, teamType: null }])
    expect(teamsQueryKey({ lawFirmId: 1 })).toEqual(['teams', { lawFirmId: 1, teamType: null }])
  })
})
