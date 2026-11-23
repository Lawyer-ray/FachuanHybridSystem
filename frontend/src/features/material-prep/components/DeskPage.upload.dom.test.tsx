// @vitest-environment jsdom
/**
 * DeskPage：加载态 / 页签过滤与计数 / 上传 / 阶段编排（jsdom）。
 *
 * 从 DeskPage.dom.test.tsx 按被测单元拆出；共用桩与渲染入口见
 * `desk-page-test-harness.tsx`，用例本身逐字搬迁。
 */
import { act, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  hookMock,
  httpError,
  lastSearch,
  pack,
  renderDesk,
  resetDeskPageMocks,
  setup,
  ui,
} from './desk-page-test-harness'

import { toast } from 'sonner'

beforeEach(resetDeskPageMocks)

describe('DeskPage：加载态布局', () => {
  it('loading 占位与空态同构（虚线容器 + 水平垂直居中），不贴左', () => {
    hookMock.useMaterialPacks.mockReturnValue({ data: undefined, isLoading: true, error: null })
    hookMock.useCreatePack.mockReturnValue({ mutateAsync: vi.fn(async () => ({})) })
    hookMock.useJudgePack.mockReturnValue({ mutateAsync: vi.fn(async () => ({})) })
    hookMock.useDeletePack.mockReturnValue({ mutateAsync: vi.fn(async () => ({})), isPending: false })
    const { container } = renderDesk()
    // 文案与 spinner 同在一个占位块里（React 把二者作为同一 div 的子节点）
    // 取「最小」的那个含该文案的 div——外层包裹 div 也含这段文字
    const box = Array.from(container.querySelectorAll('div'))
      .filter((d) => (d.textContent ?? '').includes('加载材料包'))
      .sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length)[0]!
    expect(box.className).toContain('justify-center')
    expect(box.className).toContain('items-center')
    // 与 PackGrid 空态同一视觉语言（虚线卡片框架，而非裸 div）
    expect(box.className).toContain('border-dashed')
  })
})

describe('DeskPage：页签过滤与计数', () => {
  it('默认显示 todo 页签的包', () => {
    setup([pack(1, 'todo'), pack(2, 'done'), pack(3, 'todo')])
    const { unmount } = renderDesk()
    expect(ui.grid!.packs.map((p) => p.id)).toEqual([1, 3])
    unmount()
  })

  it('三个页签各自计数', () => {
    setup([pack(1, 'todo'), pack(2, 'done'), pack(3, 'done'), pack(4, 'filed')])
    const { unmount } = renderDesk()
    // inbox 是流水线第一段，与三个材料包状态同在一级页签上，故计数一并出现
    expect(ui.tabs!.counts).toEqual({ inbox: 0, todo: 1, done: 2, filed: 1 })
    unmount()
  })

  it('切页签后显示对应状态的包', async () => {
    setup([pack(1, 'todo'), pack(2, 'done')])
    const { unmount, getByText } = renderDesk()

    act(() => {
      getByText('切到已归案').click()
    })
    await waitFor(() => expect(ui.grid!.packs.map((p) => p.id)).toEqual([2]))
    unmount()
  })

  it('数据为 null 时不崩且计数为 0', () => {
    setup(null)
    const { unmount } = renderDesk()
    expect(ui.tabs!.counts).toEqual({ inbox: 0, todo: 0, done: 0, filed: 0 })
    unmount()
  })
})

describe('DeskPage：上传', () => {
  it('上传成功提示份数', async () => {
    setup([])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('模拟上传').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已收进 2 份材料'))
    unmount()
  })

  it('上传失败提示且不抛错', async () => {
    setup([], {
      create: vi.fn(async () => {
        throw httpError(500)
      }),
    })
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('模拟上传').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('上传失败，请重试'))
    unmount()
  })

  it('上传失败：透出后端文案而不是笼统的重试提示', async () => {
    setup([], {
      create: vi.fn(async () => {
        // ky 把后端 400 体挂在 HTTPError.data 上
        throw httpError(400, { code: 'ATTACHMENT_TOO_LARGE', message: '附件过大（单个不能超过 50MB）', errors: {} })
      }),
    })
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('模拟上传').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('附件过大（单个不能超过 50MB）'))
    unmount()
  })

  it('超大文件：本地直接拦住，不发请求', async () => {
    const { createMutate } = setup([])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('上传超大').click()
      await Promise.resolve()
    })
    // 关键：白传 65MB 才被后端拒绝是本次修复要避免的浪费
    expect(createMutate).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('某某诉讼材料.pdf 过大（1.2GB），单个不能超过 1.0GB'),
    )
    unmount()
  })

  it('空文件列表不触发上传', async () => {
    const { createMutate } = setup([])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('上传空').click()
      await Promise.resolve()
    })
    expect(createMutate).not.toHaveBeenCalled()
    unmount()
  })
})

describe('DeskPage：阶段（收件箱与材料包同页）', () => {
  it('缺省即收件箱阶段：主区域渲染收件箱视图，不渲染材料包网格', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText, queryByText } = renderDesk('/material-prep')
    expect(getByText('INBOX-VIEW')).toBeTruthy()
    // 网格未被渲染 —— 收件箱是漏斗第一段，尚未进入材料包阶段
    expect(queryByText(/^GRID:/)).toBeNull()
    expect(ui.tabs!.stage).toBe('inbox')
    unmount()
  })

  it('?stage=todo 时进入材料包阶段：渲染网格、不渲染收件箱视图', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText, queryByText } = renderDesk('/material-prep?stage=todo')
    expect(queryByText('INBOX-VIEW')).toBeNull()
    expect(getByText('GRID:1')).toBeTruthy()
    unmount()
  })

  it('非法 stage 值回落收件箱（不因脏 URL 白屏）', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk('/material-prep?stage=%3Cscript%3E')
    expect(getByText('INBOX-VIEW')).toBeTruthy()
    expect(ui.tabs!.stage).toBe('inbox')
    unmount()
  })

  it('?stage=todo 直达：默认落在「待处理」而不是被弹回收件箱', () => {
    // 用户报告的「todo 进不去」现象之一：带 stage 的地址必须能直接落地。
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk('/material-prep?stage=todo')
    expect(ui.tabs!.stage).toBe('todo')
    expect(getByText('GRID:1')).toBeTruthy()
    unmount()
  })

  it('切换阶段不会抹掉其它 query（深链接 ?message= 不能被吃掉）', async () => {
    // setParams 传对象是覆盖语义，曾经会把 message 一起清掉。
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk('/material-prep?message=42')

    act(() => {
      getByText('切到待处理').click()
    })
    await waitFor(() => expect(ui.tabs!.stage).toBe('todo'))
    expect(lastSearch()).toContain('message=42')
    expect(lastSearch()).toContain('stage=todo')
    unmount()
  })

  it('上传成功后从收件箱阶段切到「待处理」（新包落在那里）', async () => {
    setup([])
    const { unmount, getByText, queryByText } = renderDesk('/material-prep')
    expect(getByText('INBOX-VIEW')).toBeTruthy()
    fireEvent.click(getByText('模拟上传'))
    await waitFor(() => expect(ui.tabs!.stage).toBe('todo'))
    expect(queryByText('INBOX-VIEW')).toBeNull()
    unmount()
  })
})
