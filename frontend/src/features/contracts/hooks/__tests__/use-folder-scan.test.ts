vi.mock('../api', () => ({
  contractApi: {
    listScanSubfolders: vi.fn().mockResolvedValue({ subfolders: [] }),
    startScan: vi.fn().mockResolvedValue({ session_id: 'sess-1' }),
    confirmScan: vi.fn().mockResolvedValue({}),
    getScanStatus: vi.fn().mockResolvedValue({ status: 'completed' }),
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

import { useFolderScan, useScanStatus } from '../use-folder-scan'

describe('contracts/hooks/use-folder-scan', () => {
  it('exports useFolderScan function', () => {
    expect(typeof useFolderScan).toBe('function')
  })

  it('exports useScanStatus function', () => {
    expect(typeof useScanStatus).toBe('function')
  })

  it('useFolderScan returns subfolders, startScan, confirmScan', () => {
    const result = useFolderScan(1)
    expect(result).toHaveProperty('subfolders')
    expect(result).toHaveProperty('startScan')
    expect(result).toHaveProperty('confirmScan')
  })

  it('useScanStatus returns query result when sessionId provided', () => {
    const result = useScanStatus(1, 'sess-1')
    expect(result).toBeDefined()
  })

  it('useScanStatus handles null sessionId', () => {
    const result = useScanStatus(1, null)
    expect(result).toBeDefined()
  })

  it('useScanStatus works with different contractId', () => {
    const result = useScanStatus(42, 'sess-2')
    expect(result).toBeDefined()
  })
})
