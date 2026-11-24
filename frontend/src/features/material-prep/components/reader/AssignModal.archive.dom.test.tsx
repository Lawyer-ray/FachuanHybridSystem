// @vitest-environment jsdom
/**
 * AssignModal 的「同时归档到案件文件夹」勾选项（jsdom）。
 *
 * 勾选项是这次归档功能的**唯一入口**：默认勾选（归案顺手落卷是常态），取消勾选
 * 必须立刻写回偏好——否则用户这次关掉、下次打开又自己勾上，等于没关掉。
 * 状态由 use-assign-launch 模块持有（原因见那边的注释），这里锁两件事：
 * 1. 新挂载的弹窗默认勾选；
 * 2. 取消勾选 → 偏好写回 → 再打开仍是未勾选。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api', () => ({
  searchCases: vi.fn(async () => []),
  assignPack: vi.fn(),
  fetchAttachmentBytes: vi.fn(),
  archiveSplitToCaseFolder: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { AssignModal } from './AssignModal'
import { isArchiveToCaseFolderEnabled, setArchiveToCaseFolderEnabled } from './use-assign-launch'

const INFOS = [{ k: '委托人', v: '张某' }] as never

function renderModal() {
  // useTypeaheadSearch 走 react-query，必须有 Provider
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const utils = render(
    <AssignModal open count={3} infos={INFOS} onCancel={vi.fn()} onConfirm={vi.fn()} />,
    { wrapper: wrap },
  )
  const checkbox = within(document.body).getByRole('checkbox', {
    name: /同时归档到案件文件夹/,
  }) as HTMLInputElement
  return { ...utils, checkbox }
}

beforeEach(() => {
  vi.clearAllMocks()
  setArchiveToCaseFolderEnabled(true)
})

describe('AssignModal：同时归档到案件文件夹', () => {
  it('默认勾选（归案顺手落卷是常态）', () => {
    const { container, checkbox } = renderModal()

    expect(checkbox.checked).toBe(true)
    expect(document.body.textContent).toContain('同时归档到案件文件夹（按案件卷宗命名）')
    container.remove()
  })

  it('取消勾选写回偏好：再打开弹窗仍是未勾选', () => {
    const first = renderModal()
    fireEvent.click(first.checkbox)

    expect(isArchiveToCaseFolderEnabled()).toBe(false)
    first.container.remove()

    const second = renderModal()
    expect(second.checkbox.checked).toBe(false)
    second.container.remove()
  })
})
