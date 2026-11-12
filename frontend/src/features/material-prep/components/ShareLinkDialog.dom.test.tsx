// @vitest-environment jsdom
/**
 * ShareLinkDialog / ShareUrlBox 测试（jsdom）。
 *
 * 契约：
 *  · 标题必填才可提交；提交后走 createUploadLink，成功即把**一次性的明文链接**
 *    交回父层并关闭弹窗（不在本弹窗里叠第二层结果视图）
 *  · 失败提示且不关闭，busy 期间按钮禁用
 *  · 有效期下拉 / 客户称呼 / 说明 / 绑定项目都进请求体；关掉再打开清空表单
 *  · 项目检索 300ms 防抖、选中回显可清除、检索失败按无结果处理
 *  · 复制走 useCopyFeedback：成功/失败都有 toast（内网 http 下没有 clipboard）
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  createUploadLink: vi.fn(),
  searchContracts: vi.fn(),
  buildShareUrl: vi.fn((token: string) => `https://share.test/u/${token}`),
}))
const copyMock = vi.hoisted(() => ({ copy: vi.fn(async () => true) }))
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.mock('../api', () => apiMock)
vi.mock('sonner', () => ({ toast: toastMock }))
vi.mock('@/hooks/use-copy-feedback', () => ({
  useCopyFeedback: () => ({ copied: copyMock.copy.mock.results.length > 0, copy: copyMock.copy }),
}))

import { ShareLinkDialog, ShareUrlBox } from './ShareLinkDialog'

function renderDialog() {
  const onOpenChange = vi.fn()
  const onCreated = vi.fn()
  const utils = render(<ShareLinkDialog open onOpenChange={onOpenChange} onCreated={onCreated} />)
  return { ...utils, onOpenChange, onCreated }
}

function titleInput(): HTMLInputElement {
  return screen.getByPlaceholderText('如：张三·买卖合同纠纷·证据材料') as HTMLInputElement
}

function submitButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /生成链接/ }) as HTMLButtonElement
}

beforeEach(() => {
  vi.clearAllMocks()
  copyMock.copy.mockResolvedValue(true)
  apiMock.createUploadLink.mockResolvedValue({ token: 'tok-1' })
  apiMock.searchContracts.mockResolvedValue([])
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ShareLinkDialog：提交', () => {
  it('标题为空时禁用「生成链接」', () => {
    renderDialog()
    expect(submitButton().disabled).toBe(true)
    fireEvent.change(titleInput(), { target: { value: '   ' } })
    // 只有空白也不算填了标题
    expect(submitButton().disabled).toBe(true)
  })

  it('填标题后可提交：请求体带齐字段，成功后把链接与标题交回父层并关闭弹窗', async () => {
    const { onOpenChange, onCreated } = renderDialog()
    fireEvent.change(titleInput(), { target: { value: '  张三·证据材料  ' } })
    fireEvent.change(screen.getByPlaceholderText('选填，如 张三'), { target: { value: '张三' } })
    fireEvent.change(screen.getByPlaceholderText(/请上传合同原件/), { target: { value: '请上传合同' } })

    await act(async () => {
      fireEvent.click(submitButton())
    })

    expect(apiMock.createUploadLink).toHaveBeenCalledWith({
      title: '张三·证据材料',
      note: '请上传合同',
      client_name: '张三',
      contract_id: null,
      expires_days: 30,
    })
    // 必须走 buildShareUrl（手抄 /u/<token> 会在路由改名后静默发出 404 链接）
    expect(onCreated).toHaveBeenCalledWith('https://share.test/u/tok-1', '张三·证据材料')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('有效期下拉切换后按所选天数提交', async () => {
    renderDialog()
    fireEvent.change(titleInput(), { target: { value: '链接' } })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '90' } })
    await act(async () => {
      fireEvent.click(submitButton())
    })
    expect(apiMock.createUploadLink.mock.calls[0]![0]).toMatchObject({ expires_days: 90 })
  })

  it('创建失败：提示错误、不关闭弹窗、busy 复位', async () => {
    apiMock.createUploadLink.mockRejectedValue({ response: { status: 500 }, message: '服务器炸了' })
    const { onOpenChange, onCreated } = renderDialog()
    fireEvent.change(titleInput(), { target: { value: '链接' } })
    await act(async () => {
      fireEvent.click(submitButton())
    })

    expect(toastMock.error).toHaveBeenCalled()
    expect(onCreated).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
    // busy 复位后按钮仍可用（标题还在）
    expect(submitButton().disabled).toBe(false)
  })

  it('busy 期间忽略重复点击（只发一次请求）', async () => {
    let resolveCreate: (v: { token: string }) => void = () => {}
    apiMock.createUploadLink.mockReturnValue(new Promise((r) => (resolveCreate = r)))
    renderDialog()
    fireEvent.change(titleInput(), { target: { value: '链接' } })

    fireEvent.click(submitButton())
    fireEvent.click(submitButton())
    expect(apiMock.createUploadLink).toHaveBeenCalledTimes(1)
    expect(submitButton().disabled).toBe(true)

    await act(async () => resolveCreate({ token: 'tok-2' }))
  })

  it('取消按钮直接关闭弹窗', () => {
    const { onOpenChange } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('重新打开时清空上一次填的内容', async () => {
    const { rerender } = render(<ShareLinkDialog open onOpenChange={vi.fn()} />)
    fireEvent.change(titleInput(), { target: { value: '上一次的标题' } })
    expect(titleInput().value).toBe('上一次的标题')

    rerender(<ShareLinkDialog open={false} onOpenChange={vi.fn()} />)
    rerender(<ShareLinkDialog open onOpenChange={vi.fn()} />)
    await waitFor(() => expect(titleInput().value).toBe(''))
  })
})

describe('ShareLinkDialog：绑定项目检索', () => {
  function contract(id: number, name: string, filing?: string) {
    return { id, name, filing_number: filing ?? '' }
  }

  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('输入关键字 300ms 防抖后检索，命中项可点选并在选中后回显、可清除', async () => {
    apiMock.searchContracts.mockResolvedValue([contract(5, '张三委托合同', 'FY-2026-001')])
    renderDialog()

    const input = screen.getByPlaceholderText(/按项目（委托合同）名称检索/)
    fireEvent.change(input, { target: { value: '张三' } })
    // 防抖期内不发请求
    expect(apiMock.searchContracts).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(apiMock.searchContracts).toHaveBeenCalledWith('张三')

    fireEvent.click(screen.getByRole('button', { name: /张三委托合同/ }))
    expect(screen.getByText('FY-2026-001')).toBeTruthy()

    // 选中后提交时带上 contract_id
    fireEvent.change(titleInput(), { target: { value: '链接' } })
    await act(async () => {
      fireEvent.click(submitButton())
    })
    expect(apiMock.createUploadLink.mock.calls[0]![0]).toMatchObject({ contract_id: 5 })

    // 清除后回到检索框
    fireEvent.click(screen.getByRole('button', { name: '清除' }))
    expect(screen.getByPlaceholderText(/按项目（委托合同）名称检索/)).toBeTruthy()
  })

  it('检索失败按无结果处理（不抛、不残留旧结果）', async () => {
    apiMock.searchContracts.mockRejectedValue(new Error('500'))
    renderDialog()
    fireEvent.change(screen.getByPlaceholderText(/按项目（委托合同）名称检索/), {
      target: { value: '张三' },
    })
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('清空关键字立即收起结果列表，不再发请求', async () => {
    apiMock.searchContracts.mockResolvedValue([contract(5, '张三委托合同')])
    renderDialog()
    const input = screen.getByPlaceholderText(/按项目（委托合同）名称检索/)
    fireEvent.change(input, { target: { value: '张三' } })
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.getByRole('list')).toBeTruthy()

    fireEvent.change(input, { target: { value: '' } })
    expect(screen.queryByRole('list')).toBeNull()
    expect(apiMock.searchContracts).toHaveBeenCalledTimes(1)
  })
})

describe('ShareUrlBox：复制反馈', () => {
  it('只读输入框展示链接，复制成功提示「已复制链接」', async () => {
    render(<ShareUrlBox url="https://share.test/u/tok-1" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    expect(input.value).toBe('https://share.test/u/tok-1')
    expect(input.readOnly).toBe(true)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /复制/ }))
    })
    expect(copyMock.copy).toHaveBeenCalledWith('https://share.test/u/tok-1')
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('已复制链接'))
  })

  it('复制失败给出可操作提示（内网 http 下没有 navigator.clipboard）', async () => {
    copyMock.copy.mockResolvedValue(false)
    render(<ShareUrlBox url="https://share.test/u/tok-2" />)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /复制/ }))
    })
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('复制失败，请手动选择复制'))
  })
})
