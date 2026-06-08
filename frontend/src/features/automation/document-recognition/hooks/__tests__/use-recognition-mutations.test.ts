vi.mock('../api', () => ({
  documentRecognitionApi: {
    upload: vi.fn().mockResolvedValue({}),
    bindCase: vi.fn().mockResolvedValue({}),
    updateRecognitionInfo: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
    useQueryClient: vi.fn().mockReturnValue({ invalidateQueries: vi.fn() }),
  }
})

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import { useUploadDocument, useBindCase, useUpdateRecognitionInfo } from '../use-recognition-mutations'

describe('automation/document-recognition/hooks/use-recognition-mutations', () => {
  it('exports useUploadDocument function', () => {
    expect(typeof useUploadDocument).toBe('function')
  })

  it('exports useBindCase function', () => {
    expect(typeof useBindCase).toBe('function')
  })

  it('exports useUpdateRecognitionInfo function', () => {
    expect(typeof useUpdateRecognitionInfo).toBe('function')
  })

  it('useUploadDocument returns mutation shape', () => {
    const result = useUploadDocument()
    expect(result).toHaveProperty('mutate')
    expect(result).toHaveProperty('isPending')
  })

  it('useBindCase returns mutation shape', () => {
    const result = useBindCase()
    expect(result).toHaveProperty('mutate')
    expect(result).toHaveProperty('isPending')
  })
})
