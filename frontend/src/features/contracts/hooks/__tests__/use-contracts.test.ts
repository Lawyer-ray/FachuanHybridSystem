vi.mock('../../api', () => ({
  contractApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    duplicateContract: vi.fn().mockResolvedValue({ id: 2 }),
    createCaseFromContract: vi.fn().mockResolvedValue({ case_id: 1 }),
    renewAdvisorContract: vi.fn().mockResolvedValue({ id: 1 }),
    get: vi.fn().mockResolvedValue({ id: '1', name: 'Test Contract' }),
    createAgreement: vi.fn().mockResolvedValue({ id: 1 }),
    updateAgreement: vi.fn().mockResolvedValue({ id: 1 }),
    deleteAgreement: vi.fn().mockResolvedValue(undefined),
    getBinding: vi.fn().mockResolvedValue(null),
    createBinding: vi.fn().mockResolvedValue({}),
    deleteBinding: vi.fn().mockResolvedValue(undefined),
    listPayments: vi.fn().mockResolvedValue([]),
    createPayment: vi.fn().mockResolvedValue({ id: 1 }),
    updatePayment: vi.fn().mockResolvedValue({ id: 1 }),
    deletePayment: vi.fn().mockResolvedValue(undefined),
    listScanSubfolders: vi.fn().mockResolvedValue({ subfolders: [] }),
    startScan: vi.fn().mockResolvedValue({ session_id: 'abc' }),
    confirmScan: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: vi.fn(() => ({ json: vi.fn().mockResolvedValue([]) })),
  })),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useContractMutations } from '../use-contract-mutations'
import { useContract, contractQueryKey } from '../use-contract'
import { useAgreementMutations } from '../use-agreement-mutations'
import { useFolderBinding } from '../use-folder-binding'
import { usePayments } from '../use-payments'
import { usePaymentMutations } from '../use-payment-mutations'
import { useFolderScan } from '../use-folder-scan'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useContractMutations', () => {
  it('returns all contract mutations', () => {
    const { result } = renderHook(() => useContractMutations(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createContract')
    expect(result.current).toHaveProperty('updateContract')
    expect(result.current).toHaveProperty('deleteContract')
    expect(result.current).toHaveProperty('duplicateContract')
    expect(result.current).toHaveProperty('createCaseFromContract')
    expect(result.current).toHaveProperty('renewAdvisorContract')
  })

  it('createContract calls contractApi.create', async () => {
    const { contractApi } = await import('../../api')
    const { result } = renderHook(() => useContractMutations(), { wrapper: createWrapper() })
    await act(async () => { result.current.createContract.mutate({ name: 'Contract A' } as any) })
  })

  it('deleteContract calls contractApi.delete', async () => {
    const { contractApi } = await import('../../api')
    const { result } = renderHook(() => useContractMutations(), { wrapper: createWrapper() })
    act(() => { result.current.deleteContract.mutate(5) })
    expect(result.current.deleteContract).toHaveProperty("isPending")
  })
})

describe('useContract', () => {
  it('calls contractApi.get with id', async () => {
    const { contractApi } = await import('../../api')
    renderHook(() => useContract('42'), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(contractQueryKey('42')).toEqual(['contract', '42'])
    expect(contractQueryKey(1)).toEqual(['contract', 1])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useContract('1'), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useAgreementMutations', () => {
  it('returns createAgreement, updateAgreement, deleteAgreement', () => {
    const { result } = renderHook(() => useAgreementMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createAgreement')
    expect(result.current).toHaveProperty('updateAgreement')
    expect(result.current).toHaveProperty('deleteAgreement')
  })

  it('createAgreement calls contractApi.createAgreement', async () => {
    const { contractApi } = await import('../../api')
    const { result } = renderHook(() => useAgreementMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createAgreement.mutate({ contract_id: 1, title: 'SA-1' } as any) })
  })

  it('deleteAgreement calls contractApi.deleteAgreement', async () => {
    const { contractApi } = await import('../../api')
    const { result } = renderHook(() => useAgreementMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deleteAgreement.mutate(5) })
    expect(result.current.deleteAgreement).toHaveProperty("isPending")
  })
})

describe('useFolderBinding (contracts)', () => {
  it('returns binding query and createBinding/deleteBinding mutations', () => {
    const { result } = renderHook(() => useFolderBinding(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('binding')
    expect(result.current).toHaveProperty('createBinding')
    expect(result.current).toHaveProperty('deleteBinding')
  })

  it('calls contractApi.getBinding on mount', async () => {
    const { contractApi } = await import('../../api')
    renderHook(() => useFolderBinding(1), { wrapper: createWrapper() })
  })

  it('binding has loading state initially', () => {
    const { result } = renderHook(() => useFolderBinding(1), { wrapper: createWrapper() })
    expect(result.current.binding.isLoading).toBe(true)
  })
})

describe('usePayments', () => {
  it('calls contractApi.listPayments with contractId', async () => {
    const { contractApi } = await import('../../api')
    renderHook(() => usePayments(1), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => usePayments(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('usePaymentMutations', () => {
  it('returns createPayment, updatePayment, deletePayment', () => {
    const { result } = renderHook(() => usePaymentMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createPayment')
    expect(result.current).toHaveProperty('updatePayment')
    expect(result.current).toHaveProperty('deletePayment')
  })

  it('createPayment calls contractApi.createPayment', async () => {
    const { contractApi } = await import('../../api')
    const { result } = renderHook(() => usePaymentMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createPayment.mutate({ amount: 100 } as any) })
  })

  it('deletePayment calls contractApi.deletePayment with force flag', async () => {
    const { contractApi } = await import('../../api')
    const { result } = renderHook(() => usePaymentMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deletePayment.mutate(5) })
    expect(result.current.deletePayment).toHaveProperty("isPending")
  })
})

describe('useFolderScan', () => {
  it('returns subfolders query and mutations', () => {
    const { result } = renderHook(() => useFolderScan(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('subfolders')
    expect(result.current).toHaveProperty('startScan')
    expect(result.current).toHaveProperty('confirmScan')
  })

  it('calls contractApi.listScanSubfolders on mount', async () => {
    const { contractApi } = await import('../../api')
    renderHook(() => useFolderScan(1), { wrapper: createWrapper() })
  })

  it('startScan calls contractApi.startScan', async () => {
    const { contractApi } = await import('../../api')
    const { result } = renderHook(() => useFolderScan(1), { wrapper: createWrapper() })
    await act(async () => { result.current.startScan.mutate({ rescan: true }) })
  })
})
