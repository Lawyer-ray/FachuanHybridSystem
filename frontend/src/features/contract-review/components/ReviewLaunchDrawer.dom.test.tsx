// @vitest-environment jsdom
/**
 * ReviewLaunchDrawer 测试（jsdom）。
 *
 * 这是「先定参数再让 AI 跑」的入口，契约错了整批建议都会方向反。
 *
 * **两阶段流程**（本轮改动）：
 * 1. 打开抽屉 → 上传并让后端识别甲乙丙丁 → 用真实当事人渲染立场选项
 * 2. 律师选立场 + 步骤 + 交代 → confirmParty 触发流水线
 *
 * 为什么必须先识别：合同可能四方、我方也可能是乙方或丙方（代表客户股东
 * 去审尤其如此）。先给「甲方/乙方」两个空标签让人选，等于让他猜。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  uploadContract: vi.fn(),
  confirmParty: vi.fn(),
  listRevisions: vi.fn(),
  resolveRevision: vi.fn(),
  getTaskStatus: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

import { confirmParty, uploadContract } from '../api'
import { ReviewLaunchDrawer } from './ReviewLaunchDrawer'

const uploadMock = vi.mocked(uploadContract)
const confirmMock = vi.mocked(confirmParty)

const FOUR_PARTIES = {
  party_a: '甲方示例科技有限公司',
  party_b: '乙方示例贸易有限公司',
  party_c: '丙方示例担保有限公司',
}

function uploaded(parties: Record<string, string> = FOUR_PARTIES) {
  return { task_id: 'task-1', status: 'parties_identified', contract_title: '设备销售合同', parties }
}

/**
 * 抽屉的「上传 + 识别」阶段由 react-query mutation 承载（旧实现是 useEffect +
 * runningRef 守卫），所以渲染必须包一层 QueryClientProvider——与 use-revisions
 * 测试同一套路。retry 关掉，否则失败用例要等退避。
 */
function setup(over: Partial<Parameters<typeof ReviewLaunchDrawer>[0]> = {}) {
  const onStarted = vi.fn()
  const onClose = vi.fn()
  const loadFile = vi.fn().mockResolvedValue(new ArrayBuffer(8))
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const ui = (props: Partial<Parameters<typeof ReviewLaunchDrawer>[0]>) => (
    <QueryClientProvider client={queryClient}>
      <ReviewLaunchDrawer
        open
        fileName="设备销售合同.docx"
        loadFile={loadFile}
        onClose={onClose}
        onStarted={onStarted}
        {...props}
      />
    </QueryClientProvider>
  )
  const { rerender } = render(ui(over))
  return {
    onStarted,
    onClose,
    loadFile,
    queryClient,
    /** 模拟同一个抽屉里换了文件（调用方原地换 fileName，不卸载抽屉） */
    rerenderWith: (props: Partial<Parameters<typeof ReviewLaunchDrawer>[0]>) => rerender(ui({ ...over, ...props })),
  }
}

beforeEach(() => {
  uploadMock.mockReset()
  confirmMock.mockReset()
  uploadMock.mockResolvedValue(uploaded())
  confirmMock.mockResolvedValue({ task_id: 'task-1', status: 'confirmed' })
})

describe('ReviewLaunchDrawer · 立场识别', () => {
  it('打开即上传识别，用真实当事人名渲染立场', async () => {
    setup()
    await waitFor(() => expect(screen.getByText('甲方')).toBeTruthy())
    expect(uploadMock).toHaveBeenCalledTimes(1)
    // 三方的名字都要出现（不是写死的甲/乙两项）
    expect(screen.getByText('甲方示例科技有限公司')).toBeTruthy()
    expect(screen.getByText('乙方示例贸易有限公司')).toBeTruthy()
    expect(screen.getByText('丙方示例担保有限公司')).toBeTruthy()
    expect(screen.getByText('丙方')).toBeTruthy()
  })

  it('识别结果里没有丙丁就不渲染丙丁', async () => {
    uploadMock.mockResolvedValue(uploaded({ party_a: 'A公司', party_b: 'B公司' }))
    setup()
    await waitFor(() => expect(screen.getByText('甲方')).toBeTruthy())
    expect(screen.queryByText('丙方')).toBeNull()
    expect(screen.queryByText('丁方')).toBeNull()
  })

  it('客户是乙方时自动推荐乙方（不写死甲方）', async () => {
    setup({ clientName: '乙方示例贸易有限公司' })
    await waitFor(() => expect(screen.getByText(/已选：乙方/)).toBeTruthy())
  })

  it('客户不在合同任一方时不自作主张，提示律师自己选', async () => {
    setup({ clientName: '完全不相干的公司' })
    await waitFor(() => expect(screen.getByText(/请选择我方代表哪一方/)).toBeTruthy())
  })

  it('无法识别当事人时给出可执行说明，而不是空白', async () => {
    uploadMock.mockResolvedValue(uploaded({}))
    setup()
    await waitFor(() => expect(screen.getByText(/没有从合同里认出当事人/)).toBeTruthy())
  })

  it('上传失败给出错误且不允许提交', async () => {
    uploadMock.mockRejectedValue(new Error('文件过大'))
    setup()
    await waitFor(() => expect(screen.getByText(/读取合同失败/)).toBeTruthy())
    const btn = screen.getByRole('button', { name: /开始审查/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})

describe('ReviewLaunchDrawer · 提交', () => {
  it('未选立场时不能提交', async () => {
    setup({ clientName: '不相干公司' })
    await waitFor(() => expect(screen.getByText(/请选择我方代表哪一方/)).toBeTruthy())
    const btn = screen.getByRole('button', { name: /开始审查/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })

  it('确认立场时复用已上传的 taskId，不重复上传', async () => {
    const { onStarted } = setup()
    await waitFor(() => expect(screen.getByText('甲方')).toBeTruthy())
    // 未传 clientName 时不会自动推荐，需律师自己点
    fireEvent.click(screen.getByRole('button', { name: /甲方/ }))

    fireEvent.click(screen.getByRole('button', { name: /开始审查/ }))
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith('task-1'))

    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(confirmMock.mock.calls[0]?.[0]).toBe('task-1')
  })

  it('我方名称取自识别结果（不是我方猜的）', async () => {
    setup({ clientName: '丙方示例担保有限公司' })
    await waitFor(() => expect(screen.getByText(/已选：丙方/)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /开始审查/ }))
    await waitFor(() => expect(confirmMock).toHaveBeenCalled())

    const payload = confirmMock.mock.calls[0]?.[1]
    expect(payload?.represented_party).toBe('party_c')
    expect(payload?.our_client_name).toBe('丙方示例担保有限公司')
  })

  it('客户交代真传给后端', async () => {
    setup()
    await waitFor(() => expect(screen.getByText('甲方')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /甲方/ }))
    fireEvent.click(screen.getByRole('button', { name: '这单一定要压工期' }))
    fireEvent.click(screen.getByRole('button', { name: /开始审查/ }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalled())
    const payload = confirmMock.mock.calls[0]?.[1]
    expect(payload?.client_note).toContain('压工期')
    expect(payload?.client_demands).toEqual(expect.arrayContaining(['这单一定要压工期']))
  })

  it('默认勾选三项审查内容', async () => {
    setup()
    await waitFor(() => expect(screen.getByText('甲方')).toBeTruthy())
    const checks = screen.getAllByRole('checkbox') as HTMLInputElement[]
    expect(checks.filter((c) => c.checked)).toHaveLength(3)
  })

  it('全不选审查内容时拦住，不发请求', async () => {
    setup()
    await waitFor(() => expect(screen.getByText('甲方')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /甲方/ }))
    const checks = screen.getAllByRole('checkbox') as HTMLInputElement[]
    for (const c of checks.filter((x) => x.checked)) fireEvent.click(c)
    fireEvent.click(screen.getByRole('button', { name: /开始审查/ }))

    await waitFor(() => expect(screen.getByText('至少选一项审查内容')).toBeTruthy())
    expect(confirmMock).not.toHaveBeenCalled()
  })

  it('关闭按钮触发 onClose', async () => {
    const { onClose } = setup()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('ReviewLaunchDrawer · 模态语义', () => {
  it('抽屉是 role=dialog + aria-modal，标题可被辅助技术读到', async () => {
    setup()
    const dialog = screen.getByRole('dialog', { name: '发起审查' })
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    await waitFor(() => expect(screen.getByText('甲方')).toBeTruthy())
  })

  it('Esc 关闭抽屉', async () => {
    const { onClose } = setup()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('Tab 到末尾后回到抽屉内第一个可聚焦元素（焦点不跑到背后页面）', async () => {
    setup()
    await waitFor(() => expect(screen.getByText('甲方')).toBeTruthy())
    const dialog = screen.getByRole('dialog')
    const focusables = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), textarea'))
    const last = focusables[focusables.length - 1]!
    last.focus()
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(dialog.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).toBe(focusables[0])
  })
})

describe('ReviewLaunchDrawer · 换文件必须重新识别', () => {
  it('同一抽屉换 fileName 后重新上传，而不是沿用上一份合同的识别结果', async () => {
    // 旧实现：runningRef 只在错误分支复位，成功路径永不复位 —— 换文件后静默不重传
    uploadMock
      .mockResolvedValueOnce(uploaded({ party_a: '旧合同甲方有限公司', party_b: '旧合同乙方有限公司' }))
      .mockResolvedValueOnce(uploaded({ party_a: '新合同甲方有限公司', party_b: '新合同乙方有限公司' }))

    const { rerenderWith } = setup()
    await waitFor(() => expect(screen.getByText('旧合同甲方有限公司')).toBeTruthy())

    rerenderWith({ fileName: '另一份合同.docx' })
    await waitFor(() => expect(screen.getByText('新合同甲方有限公司')).toBeTruthy())
    expect(screen.queryByText('旧合同甲方有限公司')).toBeNull()
    expect(uploadMock).toHaveBeenCalledTimes(2)
  })
})
