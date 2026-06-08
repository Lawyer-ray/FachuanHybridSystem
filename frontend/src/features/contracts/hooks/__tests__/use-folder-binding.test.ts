vi.mock('../api', () => ({
  contractApi: {
    getFolderBinding: vi.fn().mockResolvedValue({ binding: null }),
    bindFolder: vi.fn().mockResolvedValue({}),
    unbindFolder: vi.fn().mockResolvedValue({}),
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

  it('useFolderBinding returns query result', () => {
    const result = useFolderBinding(1)
    expect(result).toBeDefined()
  })

  it('useFolderBrowse returns query result', () => {
    const result = useFolderBrowse('/path')
    expect(result).toBeDefined()
  })
})
