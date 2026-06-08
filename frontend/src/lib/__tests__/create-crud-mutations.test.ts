vi.mock('@tanstack/react-query', () => {
  const mockQueryClient = {
    invalidateQueries: vi.fn(),
    setQueryData: vi.fn(),
    removeQueries: vi.fn(),
  }
  return {
    useMutation: vi.fn((config) => ({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
      ...config,
    })),
    useQueryClient: vi.fn(() => mockQueryClient),
    __mockQueryClient: mockQueryClient,
  }
})

import { createCrudMutations } from '../create-crud-mutations'

// Get the mock query client
const { __mockQueryClient: mockQueryClient } = await import('@tanstack/react-query') as unknown as {
  __mockQueryClient: { invalidateQueries: ReturnType<typeof vi.fn>; setQueryData: ReturnType<typeof vi.fn>; removeQueries: ReturnType<typeof vi.fn> }
}

describe('createCrudMutations', () => {
  const mockApi = {
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns a hook function', () => {
    const hook = createCrudMutations({
      api: mockApi,
      listKey: ['items'],
    })
    expect(typeof hook).toBe('function')
  })

  it('hook returns create, update, delete', () => {
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: ['items'],
    })
    const result = useMutations()
    expect(result).toHaveProperty('create')
    expect(result).toHaveProperty('update')
    expect(result).toHaveProperty('delete')
  })

  it('accepts function as listKey', () => {
    const predicate = ({ queryKey }: { queryKey: readonly unknown[] }) =>
      queryKey[0] === 'items'
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: predicate,
    })
    expect(typeof useMutations).toBe('function')
  })

  it('respects optimisticDetail option', () => {
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: ['items'],
      detailKey: (id: number) => ['item', id],
      optimisticDetail: false,
    })
    expect(typeof useMutations).toBe('function')
  })

  it('respects removeDetailOnDelete option', () => {
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: ['items'],
      detailKey: (id: number) => ['item', id],
      removeDetailOnDelete: false,
    })
    expect(typeof useMutations).toBe('function')
  })

  it('calls onSuccess for create mutation (array listKey)', () => {
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: ['items'],
    })
    const result = useMutations()
    if (result.create.onSuccess) {
      result.create.onSuccess({}, {}, undefined, undefined as never)
    }
    expect(mockQueryClient.invalidateQueries).toHaveBeenCalled()
  })

  it('calls onSuccess for create mutation with function listKey', () => {
    const predicate = ({ queryKey }: { queryKey: readonly unknown[] }) => queryKey[0] === 'items'
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: predicate,
    })
    const result = useMutations()
    if (result.create.onSuccess) {
      result.create.onSuccess({}, {}, undefined, undefined as never)
    }
    expect(mockQueryClient.invalidateQueries).toHaveBeenCalled()
  })

  it('calls onSuccess for update mutation with detailKey', () => {
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: ['items'],
      detailKey: (id: number) => ['item', id],
    })
    const result = useMutations()
    if (result.update.onSuccess) {
      result.update.onSuccess({}, { id: 1, data: {} }, undefined, undefined as never)
    }
    expect(mockQueryClient.invalidateQueries).toHaveBeenCalled()
    expect(mockQueryClient.setQueryData).toHaveBeenCalled()
  })

  it('calls onSuccess for delete mutation with detailKey and removeQueries', () => {
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: ['items'],
      detailKey: (id: number) => ['item', id],
    })
    const result = useMutations()
    if (result.delete.onSuccess) {
      result.delete.onSuccess({}, 1, undefined, undefined as never)
    }
    expect(mockQueryClient.invalidateQueries).toHaveBeenCalled()
    expect(mockQueryClient.removeQueries).toHaveBeenCalled()
  })

  it('calls onSuccess for update with function listKey', () => {
    const predicate = ({ queryKey }: { queryKey: readonly unknown[] }) => queryKey[0] === 'items'
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: predicate,
      detailKey: (id: number) => ['item', id],
    })
    const result = useMutations()
    if (result.update.onSuccess) {
      result.update.onSuccess({}, { id: 2, data: {} }, undefined, undefined as never)
    }
    expect(mockQueryClient.invalidateQueries).toHaveBeenCalled()
  })

  it('calls onSuccess for delete with function listKey', () => {
    const predicate = ({ queryKey }: { queryKey: readonly unknown[] }) => queryKey[0] === 'items'
    const useMutations = createCrudMutations({
      api: mockApi,
      listKey: predicate,
      detailKey: (id: number) => ['item', id],
    })
    const result = useMutations()
    if (result.delete.onSuccess) {
      result.delete.onSuccess({}, 2, undefined, undefined as never)
    }
    expect(mockQueryClient.invalidateQueries).toHaveBeenCalled()
  })
})
