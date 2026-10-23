// @vitest-environment jsdom
/**
 * CopilotEmbed（详情页专属 AI 工作区的对话区）测试（jsdom）：
 * 挂载时的业务上下文绑定（不匹配才进入、匹配则不打断当前会话）、
 * header 动作（历史 / 材料[仅合同] / 新对话）、拖拽投放双通道。
 * store 与重组件 mock 成占位，只测嵌入壳的编排。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const copilotState = vi.hoisted(() => ({
  context: null as { origin: 'case' | 'contract'; refId: number; title: string } | null,
  addAttachmentFiles: vi.fn(),
  addFolderRef: vi.fn(),
  enterContext: vi.fn(),
  switchSession: vi.fn(),
}))

vi.mock('../store', () => ({
  useCopilot: Object.assign(
    (selector: (s: typeof copilotState) => unknown) => selector(copilotState),
    {
      getState: () => copilotState,
      setState: (patch: Partial<typeof copilotState>) => void Object.assign(copilotState, patch),
    },
  ),
}))

vi.mock('./MessageList', () => ({ MessageList: () => <div data-testid="msg-list" /> }))
vi.mock('./Composer', () => ({ Composer: () => <div data-testid="composer" /> }))
vi.mock('./SessionSidebar', () => ({ SessionSidebar: () => <div data-testid="session-sidebar" /> }))
vi.mock('./FolderTreeDrawer', () => ({
  FolderTreeDrawer: () => <div data-testid="folder-drawer" />,
}))

import { CopilotEmbed } from './CopilotEmbed'
import { FOLDER_REF_MIME } from '../types'

beforeEach(() => {
  copilotState.context = null
  copilotState.enterContext = vi.fn()
  copilotState.switchSession = vi.fn()
  copilotState.addFolderRef = vi.fn()
  copilotState.addAttachmentFiles = vi.fn()
})

describe('CopilotEmbed 上下文绑定', () => {
  it('挂载且当前范围不匹配时进入业务上下文', () => {
    render(<CopilotEmbed origin="contract" refId={8} title="某银行与某公司" />)
    expect(copilotState.enterContext).toHaveBeenCalledWith({
      origin: 'contract',
      refId: 8,
      title: '某银行与某公司',
    })
  })

  it('已在同一业务范围时不重进（不打断全局面板延续过来的当前会话）', () => {
    copilotState.context = { origin: 'contract', refId: 8, title: '旧标题也无所谓' }
    render(<CopilotEmbed origin="contract" refId={8} title="某银行与某公司" />)
    expect(copilotState.enterContext).not.toHaveBeenCalled()
  })

  it('refId 不同视为范围切换，重进', () => {
    copilotState.context = { origin: 'contract', refId: 7, title: '另一个委托' }
    render(<CopilotEmbed origin="contract" refId={8} title="某银行与某公司" />)
    expect(copilotState.enterContext).toHaveBeenCalledTimes(1)
  })
})

describe('CopilotEmbed 壳编排', () => {
  it('渲染消息区与输入区；合同范围有材料按钮，案件范围没有', () => {
    const { rerender } = render(<CopilotEmbed origin="contract" refId={8} title="某银行" />)
    expect(screen.getByTestId('msg-list')).toBeTruthy()
    expect(screen.getByTestId('composer')).toBeTruthy()
    expect(screen.getByRole('button', { name: '展开合同材料目录' })).toBeTruthy()

    rerender(<CopilotEmbed origin="case" refId={386} title="某案" />)
    expect(screen.queryByRole('button', { name: '展开合同材料目录' })).toBeNull()
  })

  it('「新对话」重置会话并收起历史列表', () => {
    render(<CopilotEmbed origin="contract" refId={8} title="某银行" />)
    fireEvent.click(screen.getByRole('button', { name: '查看本范围的会话列表' }))
    expect(screen.getByTestId('session-sidebar')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '开始新对话' }))
    expect(copilotState.switchSession).toHaveBeenCalledWith(null)
    expect(screen.queryByTestId('session-sidebar')).toBeNull()
  })
})

describe('CopilotEmbed 拖拽投放', () => {
  it('自定义 MIME 投放成引用（不进文件上传通道）', () => {
    render(<CopilotEmbed origin="contract" refId={8} title="某银行" />)
    const zone = screen.getByRole('region', { name: '法穿SI超级助理' })
    fireEvent.drop(zone, {
      dataTransfer: {
        getData: (mime: string) =>
          mime === FOLDER_REF_MIME
            ? JSON.stringify({ kind: 'contract', ownerId: 8, subpath: '1-一审/起诉状.pdf', name: '起诉状.pdf' })
            : '',
        files: [],
      },
    })
    expect(copilotState.addFolderRef).toHaveBeenCalledWith({
      kind: 'contract',
      ownerId: 8,
      subpath: '1-一审/起诉状.pdf',
      name: '起诉状.pdf',
    })
    expect(copilotState.addAttachmentFiles).not.toHaveBeenCalled()
  })

  it('原生文件投放进上传通道', () => {
    render(<CopilotEmbed origin="contract" refId={8} title="某银行" />)
    const zone = screen.getByRole('region', { name: '法穿SI超级助理' })
    const file = new File(['x'], 'a.txt', { type: 'text/plain' })
    fireEvent.drop(zone, { dataTransfer: { getData: () => '', files: [file] } })
    expect(copilotState.addAttachmentFiles).toHaveBeenCalledWith([file])
  })
})
