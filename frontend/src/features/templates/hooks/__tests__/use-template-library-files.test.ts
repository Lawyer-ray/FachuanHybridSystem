vi.mock('../api', () => ({
  templateApi: {
    listLibraryFiles: vi.fn().mockResolvedValue([
      { path: '/templates/contract.docx', name: 'contract.docx' },
    ]),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  }
})

import { useTemplateLibraryFiles } from '../use-template-library-files'

describe('templates/hooks/use-template-library-files', () => {
  it('exports useTemplateLibraryFiles function', () => {
    expect(typeof useTemplateLibraryFiles).toBe('function')
  })
})
