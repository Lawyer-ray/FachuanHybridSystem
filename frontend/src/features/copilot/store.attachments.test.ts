import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import type { AgentSession } from './types'

vi.mock('./api', () => ({
  createSession: vi.fn(),
  fetchHistory: vi.fn(),
  openMessageStream: vi.fn(),
  decideApproval: vi.fn(),
  listSessions: vi.fn(),
  deleteSession: vi.fn(),
  steerSession: vi.fn(),
  clearSessionQueue: vi.fn(),
  submitAgentTask: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  uploadAttachment: vi.fn(),
}))

const encoder = new TextEncoder()

/** 把一组 SSE 帧包成真实 Response（body 为 ReadableStream） */
function sseResponse(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame))
      controller.close()
    },
  })
  return new Response(body, { status: 200 })
}

const session: AgentSession = {
  session_id: 's-1',
  title: '',
  status: 'active',
  llm_model: '',
  created_at: '',
  updated_at: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
})

function makeFile(name: string, size = 10, type = 'text/plain'): File {
  return new File(['x'.repeat(size)], name, { type })
}

describe('copilot store：附件', () => {
  it('addAttachmentFiles：合规收下、不合规拒绝并提示', () => {
    const good = makeFile('合同.pdf', 100)
    const badExt = makeFile('恶意.exe', 10)
    const empty = makeFile('空.txt', 0)
    useCopilot.getState().addAttachmentFiles([good, badExt, empty])

    const { pendingFiles, lastError } = useCopilot.getState()
    expect(pendingFiles.map((f) => f.name)).toEqual(['合同.pdf'])
    expect(lastError).toContain('恶意.exe')
    expect(lastError).toContain('空.txt')
  })

  it('removeAttachmentFile 按下标移除', () => {
    useCopilot.setState({ pendingFiles: [makeFile('a.txt'), makeFile('b.txt')] })
    useCopilot.getState().removeAttachmentFile(0)
    expect(useCopilot.getState().pendingFiles.map((f) => f.name)).toEqual(['b.txt'])
  })

  it('发送时先上传附件，消息附引用块，chips 清空', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.uploadAttachment).mockImplementation(async (_sid, file) => ({
      attachment_id: `att-${file.name}`,
      filename: file.name,
      size: file.size,
      mime: 'text/plain',
    }))
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"done"}\n\n']),
    )
    useCopilot.setState({ pendingFiles: [makeFile('笔记.txt', 8)] })

    await useCopilot.getState().send('帮我看看')
    expect(copilotApi.uploadAttachment).toHaveBeenCalledWith('s-1', expect.any(File))
    const user = useCopilot.getState().messages.find((m) => m.role === 'user')!
    expect(user.content).toContain('[已上传附件：笔记.txt (attachment_id=att-笔记.txt)]')
    expect(useCopilot.getState().pendingFiles).toEqual([])
  })

  it('附件上传失败：不发消息、chips 保留可重试', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.uploadAttachment).mockRejectedValue(new Error('boom'))
    const file = makeFile('笔记.txt', 8)
    useCopilot.setState({ pendingFiles: [file] })

    await useCopilot.getState().send('帮我看看')
    expect(copilotApi.openMessageStream).not.toHaveBeenCalled()
    expect(useCopilot.getState().lastError).toContain('准备失败')
    expect(useCopilot.getState().pendingFiles).toEqual([file])
    expect(useCopilot.getState().streaming).toBe(false)
    // 早退必须清锁，否则一次上传失败就把发送钮永久置忙
    expect(useCopilot.getState().sending).toBe(false)
  })

  it('上传在途时 send 不可重入：sending 置位、第二次 send 不触发第二次开流', async () => {
    // 回归 P1-4：uploadingAttachments 在 await 后立刻置 false，而消息入列在
    // 其后、streaming 仍是 false——三个按钮同时解锁，二次提交会把同一批附件
    // 再传一遍并往转录里慂两条消息。sending 必须贯穿到消息入列
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    let releaseUpload: () => void = () => {}
    vi.mocked(copilotApi.uploadAttachment).mockImplementation(
      (_sid, file) =>
        new Promise((resolve) => {
          releaseUpload = () =>
            resolve({ attachment_id: `att-${file.name}`, filename: file.name, size: file.size, mime: 'text/plain' })
        }),
    )
    vi.mocked(copilotApi.openMessageStream).mockImplementation(() =>
      Promise.resolve(sseResponse(['data: {"type":"done"}\n\n'])),
    )
    useCopilot.setState({ pendingFiles: [makeFile('笔记.txt', 8)] })

    const first = useCopilot.getState().send('帮我看看')
    // 上传 promise 未 resolve：锁必须在位（此时 streaming 还是 false）
    await vi.waitFor(() => expect(copilotApi.uploadAttachment).toHaveBeenCalled())
    expect(useCopilot.getState().sending).toBe(true)
    expect(useCopilot.getState().streaming).toBe(false)

    // 第二次提交：直接退回，onQueued(false)（Composer 据此回填正文）
    const onQueued = vi.fn()
    await useCopilot.getState().send('帮我看看', onQueued)
    expect(onQueued).toHaveBeenCalledWith(false)
    expect(copilotApi.uploadAttachment).toHaveBeenCalledTimes(1)
    expect(copilotApi.openMessageStream).not.toHaveBeenCalled()

    // 放行上传：第一次发送正常入列开流，只产出一对 user/assistant 气泡
    releaseUpload()
    await first
    expect(copilotApi.openMessageStream).toHaveBeenCalledTimes(1)
    expect(useCopilot.getState().messages.map((m) => m.role)).toEqual(['user', 'assistant'])
    // 交给 streaming 后锁已解除，本轮结束后可再次发送
    expect(useCopilot.getState().sending).toBe(false)
    expect(useCopilot.getState().streaming).toBe(false)
  })
})

// ============ 僵尸审批卡治理（B2-4 兜底） ============
