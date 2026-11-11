// @vitest-environment jsdom
/**
 * ShareLinkPanel 测试（jsdom）。
 *
 * 契约（每条都是产品决定，不是实现细节）：
 *  · 列表行展示状态文案 / 已收统计 / 到期日；加载中与空态各有提示
 *  · 只有 open 行能「换发」「作废」「删除」；已失效行只剩删除（不必再作废）
 *  · 换发 / 作废是破坏性操作：先就地二次确认，确认后才打接口
 *  · 换发结果**就地显示在那一行**并点名标题（多行时不会搞混新链接属于谁）
 *  · 「新建链接」先收起面板再开子弹窗；子弹窗关闭回来后重新打开面板且保留刚生成的链接
 *  · 删除 404 给明确文案（后端对非本人/非管理员一律 404）
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listUploadLinks: vi.fn(),
  revokeUploadLink: vi.fn(),
  rotateUploadLink: vi.fn(),
  deleteUploadLink: vi.fn(),
  buildShareUrl: vi.fn((token: string) => `https://share.test/u/${token}`),
  createUploadLink: vi.fn(),
  searchContracts: vi.fn(),
}))
/** sonner 的 toast 本身可调用（toast('已作废…')），同时也挂 success / error */
const toastMock = vi.hoisted(() => {
  const fn = Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() })
  return { toast: fn }
})
const copyMock = vi.hoisted(() => ({ copy: vi.fn(async () => true) }))

vi.mock('../api', () => apiMock)
vi.mock('sonner', () => ({ toast: toastMock.toast }))
// 子弹窗换成可探桩：点「模拟创建成功」等价于子组件 onCreated + 关闭
vi.mock('./ShareLinkDialog', () => ({
  ShareLinkDialog: ({
    open,
    onOpenChange,
    onCreated,
  }: {
    open: boolean
    onOpenChange: (v: boolean) => void
    onCreated?: (url: string, title: string) => void
  }) =>
    open ? (
      <div data-testid="create-dialog">
        <button
          type="button"
          onClick={() => {
            onCreated?.('https://share.test/u/new-tok', '新建的链接')
            onOpenChange(false)
          }}
        >
          模拟创建成功
        </button>
      </div>
    ) : null,
  // 一次性链接框是纯展示组件，保留真实实现（换发/新建结果的断言要看它）
  ShareUrlBox: ({ url }: { url: string }) => <input readOnly value={url} />,
}))
vi.mock('@/hooks/use-copy-feedback', () => ({ useCopyFeedback: () => ({ copied: false, copy: copyMock.copy }) }))

import { ShareLinkPanel } from './ShareLinkPanel'

function row(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    title: '张三·证据材料',
    note: '',
    client_name: '张三',
    contract_id: null,
    contract_name: '张三委托合同',
    status: 'active',
    state: 'open',
    expires_at: '2026-12-01T00:00:00',
    created_at: '2026-11-01T00:00:00',
    pack_count: 2,
    used_bytes: 2048,
    quota_total_bytes: 0,
    quota_max_packs: 0,
    ...over,
  }
}

function renderPanel() {
  const onOpenChange = vi.fn()
  const utils = render(<ShareLinkPanel open onOpenChange={onOpenChange} />)
  return { ...utils, onOpenChange }
}

beforeEach(() => {
  // vi.clearAllMocks 只清 vi.fn 自身的记录；toast 的嵌套 spy 需要显式复位，
  // 否则第二组用例里 toastMock.toast.success 会变成「不是 spy」
  vi.clearAllMocks()
  toastMock.toast.mockClear()
  toastMock.toast.success.mockClear()
  toastMock.toast.error.mockClear()
  apiMock.listUploadLinks.mockResolvedValue([row()])
  apiMock.revokeUploadLink.mockResolvedValue(row({ state: 'revoked' }))
  apiMock.rotateUploadLink.mockResolvedValue({ token: 'rot-tok' })
  apiMock.deleteUploadLink.mockResolvedValue(undefined)
})

describe('ShareLinkPanel：列表', () => {
  it('加载中显示占位，随后渲染行：标题 / 状态 / 已收统计 / 到期日', async () => {
    apiMock.listUploadLinks.mockReturnValue(new Promise(() => {}))
    renderPanel()
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('行内容：客户称呼、合同名、已收包数、到期日', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText('张三·证据材料')).toBeTruthy())
    expect(screen.getByText('可收')).toBeTruthy()
    const meta = screen.getByText(/已收 2 包/)
    expect(meta.textContent).toContain('张三')
    expect(meta.textContent).toContain('张三委托合同')
    expect(meta.textContent).toContain('到期')
  })

  it('空列表显示「还没有生成过链接」', async () => {
    apiMock.listUploadLinks.mockResolvedValue([])
    renderPanel()
    await waitFor(() => expect(screen.getByText('还没有生成过链接')).toBeTruthy())
  })

  it('列表加载失败提示错误', async () => {
    apiMock.listUploadLinks.mockRejectedValue(new Error('500'))
    renderPanel()
    await waitFor(() => expect(toastMock.toast.error).toHaveBeenCalledWith('链接列表加载失败'))
  })

  it('已失效（非 open）的行只剩删除按钮，没有换发/作废', async () => {
    apiMock.listUploadLinks.mockResolvedValue([row({ state: 'expired' })])
    renderPanel()
    await waitFor(() => expect(screen.getByText('已过期')).toBeTruthy())
    expect(screen.getByRole('button', { name: /删除/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /换发新链接/ })).toBeNull()
    expect(screen.queryByRole('button', { name: '作废' })).toBeNull()
  })

  it('面板关闭时不拉列表', () => {
    render(<ShareLinkPanel open={false} onOpenChange={vi.fn()} />)
    expect(apiMock.listUploadLinks).not.toHaveBeenCalled()
  })
})

describe('ShareLinkPanel：作废（破坏性操作先确认）', () => {
  it('点「作废」先出现确认，确认后才调接口并刷新列表', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText('张三·证据材料')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: '作废' }))
    expect(apiMock.revokeUploadLink).not.toHaveBeenCalled()
    expect(screen.getByText(/作废后客户手里的链接立即失效，确定？/)).toBeTruthy()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '确认作废' }))
    })
    expect(apiMock.revokeUploadLink).toHaveBeenCalledWith(1)
    await waitFor(() => expect(toastMock.toast).toHaveBeenCalledWith('已作废，客户手里的旧链接立即失效'))
    expect(apiMock.listUploadLinks).toHaveBeenCalledTimes(2)
  })

  it('确认态可以取消，取消后什么也不做', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText('张三·证据材料')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '作废' }))
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(screen.getByRole('button', { name: '作废' })).toBeTruthy()
    expect(apiMock.revokeUploadLink).not.toHaveBeenCalled()
  })

  it('作废失败提示重试', async () => {
    apiMock.revokeUploadLink.mockRejectedValue(new Error('500'))
    renderPanel()
    await waitFor(() => expect(screen.getByText('张三·证据材料')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '作废' }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '确认作废' }))
    })
    await waitFor(() => expect(toastMock.toast.error).toHaveBeenCalledWith('作废失败，请重试'))
  })
})

describe('ShareLinkPanel：换发', () => {
  it('确认换发后就地显示新链接，并点名该行标题', async () => {
    apiMock.listUploadLinks.mockResolvedValue([row({ id: 1 }), row({ id: 2, title: '李四·合同原件' })])
    renderPanel()
    await waitFor(() => expect(screen.getByText('李四·合同原件')).toBeTruthy())

    // 第 2 行点换发 → 只出现一条确认文案，且点名第 2 行
    const rotateButtons = screen.getAllByRole('button', { name: /换发新链接/ })
    fireEvent.click(rotateButtons[1]!)
    expect(screen.getByText(/换发会让/).textContent).toContain('李四·合同原件')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '确认换发' }))
    })
    expect(apiMock.rotateUploadLink).toHaveBeenCalledWith(2)

    await waitFor(() =>
      expect(screen.getByText('「李四·合同原件」的新链接已生成，旧链接已失效')).toBeTruthy(),
    )
    // 链接走 buildShareUrl
    expect(apiMock.buildShareUrl).toHaveBeenCalledWith('rot-tok')
    expect((screen.getByDisplayValue('https://share.test/u/rot-tok') as HTMLInputElement).value).toBe(
      'https://share.test/u/rot-tok',
    )
    // 确认态收起，回到常规操作组
    expect(screen.queryByRole('button', { name: '确认换发' })).toBeNull()
  })

  it('换发失败提示错误并收起确认态', async () => {
    apiMock.rotateUploadLink.mockRejectedValue(new Error('500'))
    renderPanel()
    await waitFor(() => expect(screen.getByText('张三·证据材料')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /换发新链接/ }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '确认换发' }))
    })
    await waitFor(() => expect(toastMock.toast.error).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: /换发新链接/ })).toBeTruthy()
  })
})

describe('ShareLinkPanel：删除', () => {
  it('确认删除后调接口并点名标题提示', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText('张三·证据材料')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /删除/ }))
    expect(screen.getByText(/将不再出现在列表里/).textContent).toContain('张三·证据材料')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    })
    expect(apiMock.deleteUploadLink).toHaveBeenCalledWith(1)
    await waitFor(() => expect(toastMock.toast).toHaveBeenCalledWith('已删除「张三·证据材料」'))
  })

  it('404 给「仅创建人或管理员可删」的明确文案，而不是笼统报错', async () => {
    apiMock.deleteUploadLink.mockRejectedValue({ response: { status: 404 } })
    renderPanel()
    await waitFor(() => expect(screen.getByText('张三·证据材料')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /删除/ }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    })
    await waitFor(() =>
      expect(toastMock.toast.error).toHaveBeenCalledWith('无权删除该链接（仅创建人或管理员可删）'),
    )
  })
})

describe('ShareLinkPanel：新建链接', () => {
  it('先收起面板再开子弹窗；创建成功回到面板并保留一次性链接', async () => {
    const { onOpenChange } = renderPanel()
    await waitFor(() => expect(screen.getByText('张三·证据材料')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /新建链接/ }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(screen.getByTestId('create-dialog')).toBeTruthy()

    // 面板的 Radix 弹窗会把兄弟节点标成 aria-hidden，按 testid 取按钮
    const dialog = screen.getByTestId('create-dialog')
    const createBtn = dialog.querySelector('button')!
    await act(async () => {
      fireEvent.click(createBtn)
    })
    // 子弹窗关闭 → 回到面板
    expect(onOpenChange).toHaveBeenLastCalledWith(true)
    await waitFor(() => expect(screen.getByText('「新建的链接」的链接已生成')).toBeTruthy())
    expect(screen.getByDisplayValue('https://share.test/u/new-tok')).toBeTruthy()
    // 一次性明文提示条写明关掉就看不到了
    expect(screen.getByText(/关掉这个面板后就看不到了/)).toBeTruthy()
  })
})
