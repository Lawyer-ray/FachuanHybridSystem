const { mockInvalidateQueries, mockRemoveQueries, mockSetQueryData, mockLawyerApiCreate, mockLawyerApiUpdate, mockLawyerApiDelete, mockUseMutation, mockUseQueryClient } = vi.hoisted(() => ({
  mockInvalidateQueries: vi.fn(),
  mockRemoveQueries: vi.fn(),
  mockSetQueryData: vi.fn(),
  mockLawyerApiCreate: vi.fn().mockResolvedValue({ id: 1 }),
  mockLawyerApiUpdate: vi.fn().mockResolvedValue({ id: 1 }),
  mockLawyerApiDelete: vi.fn().mockResolvedValue(undefined),
  mockUseMutation: vi.fn(),
  mockUseQueryClient: vi.fn(),
}))

vi.mock('../../api', () => ({
  lawyerApi: {
    create: mockLawyerApiCreate,
    update: mockLawyerApiUpdate,
    delete: mockLawyerApiDelete,
  },
}))

vi.mock('../use-lawyer', () => ({
  lawyerQueryKey: (id: number) => ['lawyer', id],
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useMutation: mockUseMutation,
    useQueryClient: mockUseQueryClient,
  }
})

import { useLawyerMutations } from '../use-lawyer-mutations'

describe('organization/hooks/use-lawyer-mutations', () => {
  let mutationConfigs: Record<string, any> = {}

  beforeEach(() => {
    vi.clearAllMocks()
    mutationConfigs = {}
    let mutationIndex = 0
    mockUseQueryClient.mockReturnValue({
      invalidateQueries: mockInvalidateQueries,
      removeQueries: mockRemoveQueries,
      setQueryData: mockSetQueryData,
    })
    mockUseMutation.mockImplementation((config: any) => {
      const idx = mutationIndex++
      mutationConfigs[idx] = config
      return {
        mutate: vi.fn(),
        isPending: false,
      }
    })
  })

  it('exports useLawyerMutations function', () => {
    expect(typeof useLawyerMutations).toBe('function')
  })

  it('returns create, update, and delete mutations', () => {
    const result = useLawyerMutations()
    expect(result).toHaveProperty('createLawyer')
    expect(result).toHaveProperty('updateLawyer')
    expect(result).toHaveProperty('deleteLawyer')
  })

  it('createLawyer mutationFn calls lawyerApi.create', async () => {
    useLawyerMutations()
    const config = mutationConfigs[0]
    const params = { data: { username: 'test', password: '123456' }, licensePdf: undefined, avatar: undefined }
    await config.mutationFn(params)
    expect(mockLawyerApiCreate).toHaveBeenCalledWith(params.data, undefined, undefined)
  })

  it('createLawyer mutationFn passes licensePdf and avatar', async () => {
    useLawyerMutations()
    const config = mutationConfigs[0]
    const pdf = new File(['pdf'], 'l.pdf', { type: 'application/pdf' })
    const avatar = new File(['img'], 'a.jpg', { type: 'image/jpeg' })
    const params = { data: { username: 'test', password: '123456' }, licensePdf: pdf, avatar }
    await config.mutationFn(params)
    expect(mockLawyerApiCreate).toHaveBeenCalledWith(params.data, pdf, avatar)
  })

  it('createLawyer onSuccess invalidates queries', () => {
    useLawyerMutations()
    const config = mutationConfigs[0]
    config.onSuccess()
    expect(mockInvalidateQueries).toHaveBeenCalledWith({
      predicate: expect.any(Function),
    })
  })

  it('createLawyer predicate matches lawyers key', () => {
    useLawyerMutations()
    const config = mutationConfigs[0]
    config.onSuccess()
    const predicate = mockInvalidateQueries.mock.calls[0][0].predicate
    expect(predicate({ queryKey: ['lawyers'] })).toBe(true)
    expect(predicate({ queryKey: ['other'] })).toBe(false)
    expect(predicate({ queryKey: 'not-array' })).toBe(false)
  })

  it('updateLawyer mutationFn calls lawyerApi.update', async () => {
    useLawyerMutations()
    const config = mutationConfigs[1]
    const params = { id: 5, data: { real_name: '张三' }, licensePdf: undefined, avatar: undefined }
    await config.mutationFn(params)
    expect(mockLawyerApiUpdate).toHaveBeenCalledWith(5, params.data, undefined, undefined)
  })

  it('updateLawyer mutationFn passes files', async () => {
    useLawyerMutations()
    const config = mutationConfigs[1]
    const pdf = new File(['pdf'], 'l.pdf', { type: 'application/pdf' })
    const avatar = new File(['img'], 'a.jpg', { type: 'image/jpeg' })
    const params = { id: 5, data: { real_name: '张三' }, licensePdf: pdf, avatar }
    await config.mutationFn(params)
    expect(mockLawyerApiUpdate).toHaveBeenCalledWith(5, params.data, pdf, avatar)
  })

  it('updateLawyer onSuccess invalidates queries and sets cache', () => {
    useLawyerMutations()
    const config = mutationConfigs[1]
    const updatedLawyer = { id: 5, username: 'test' }
    config.onSuccess(updatedLawyer, { id: 5 })
    expect(mockInvalidateQueries).toHaveBeenCalledTimes(2)
    expect(mockSetQueryData).toHaveBeenCalledWith(['lawyer', 5], updatedLawyer)
  })

  it('updateLawyer predicate matches lawyers key', () => {
    useLawyerMutations()
    const config = mutationConfigs[1]
    config.onSuccess({ id: 1 }, { id: 1 })
    const predicate = mockInvalidateQueries.mock.calls[0][0].predicate
    expect(predicate({ queryKey: ['lawyers'] })).toBe(true)
    expect(predicate({ queryKey: ['other'] })).toBe(false)
  })

  it('deleteLawyer mutationFn calls lawyerApi.delete', async () => {
    useLawyerMutations()
    const config = mutationConfigs[2]
    await config.mutationFn(7)
    expect(mockLawyerApiDelete).toHaveBeenCalledWith(7)
  })

  it('deleteLawyer onSuccess invalidates and removes queries', () => {
    useLawyerMutations()
    const config = mutationConfigs[2]
    config.onSuccess(undefined, 7)
    expect(mockInvalidateQueries).toHaveBeenCalledWith({
      predicate: expect.any(Function),
    })
    expect(mockRemoveQueries).toHaveBeenCalledWith({
      queryKey: ['lawyer', 7],
    })
  })

  it('deleteLawyer predicate matches lawyers key', () => {
    useLawyerMutations()
    const config = mutationConfigs[2]
    config.onSuccess(undefined, 1)
    const predicate = mockInvalidateQueries.mock.calls[0][0].predicate
    expect(predicate({ queryKey: ['lawyers'] })).toBe(true)
    expect(predicate({ queryKey: ['credentials'] })).toBe(false)
    expect(predicate({ queryKey: 'not-array' as any })).toBe(false)
  })
})
