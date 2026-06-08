vi.mock('../api', () => ({
  contractApi: {
    getBinding: vi.fn().mockResolvedValue({ binding: null }),
    createBinding: vi.fn().mockResolvedValue({}),
    deleteBinding: vi.fn().mockResolvedValue({}),
    browseFolders: vi.fn().mockResolvedValue({ entries: [], path: '/' }),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: null, isLoading: false }),
    useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
    useQueryClient: vi.fn().mockReturnValue({ invalidateQueries: vi.fn() }),
  }
})

import { useFolderBinding, useFolderBrowse } from '../use-folder-binding'

describe('contracts/hooks/use-folder-binding', () => {
  it('exports useFolderBinding function', () => {
    expect(typeof useFolderBinding).toBe('function')
  })

  it('exports useFolderBrowse function', () => {
    expect(typeof useFolderBrowse).toBe('function')
  })

  it('useFolderBinding returns binding, createBinding, deleteBinding', () => {
    const result = useFolderBinding(1)
    expect(result).toHaveProperty('binding')
    expect(result).toHaveProperty('createBinding')
    expect(result).toHaveProperty('deleteBinding')
  })

  it('useFolderBrowse returns query result with default path', () => {
    const result = useFolderBrowse()
    expect(result).toBeDefined()
    expect(result).toHaveProperty('data')
  })

  it('useFolderBrowse accepts path parameter', () => {
    const result = useFolderBrowse('/home/user/docs')
    expect(result).toBeDefined()
  })

  it('useFolderBrowse accepts storageType parameter', () => {
    const result = useFolderBrowse('/path', 'oss')
    expect(result).toBeDefined()
  })

  it('useFolderBrowse accepts storageAccountId parameter', () => {
    const result = useFolderBrowse('/path', 'oss', 5)
    expect(result).toBeDefined()
  })

  it('useFolderBinding returns query result', () => {
    const result = useFolderBinding(1)
    expect(result).toBeDefined()
  })
})
