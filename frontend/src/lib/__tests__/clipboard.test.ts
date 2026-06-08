import { toast } from 'sonner'

import { copyToClipboard } from '../clipboard'

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('copyToClipboard', () => {
  const writeTextMock = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('navigator', {
      clipboard: { writeText: writeTextMock },
    })
  })

  it('copies text and shows success toast', async () => {
    writeTextMock.mockResolvedValue(undefined)
    await copyToClipboard('hello')
    expect(writeTextMock).toHaveBeenCalledWith('hello')
    expect(toast.success).toHaveBeenCalledWith('已复制')
  })

  it('uses custom message', async () => {
    writeTextMock.mockResolvedValue(undefined)
    await copyToClipboard('test', 'Copied!')
    expect(toast.success).toHaveBeenCalledWith('Copied!')
  })

  it('shows error toast on failure', async () => {
    writeTextMock.mockRejectedValue(new Error('fail'))
    await copyToClipboard('text')
    expect(toast.error).toHaveBeenCalledWith('复制失败')
  })
})
