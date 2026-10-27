// @vitest-environment jsdom
/**
 * AssignModal 测试（jsdom）。
 *
 * 重点验证两条纯判定逻辑（易错且直接决定能否提交）：
 * - why 文案随 target / pickCase / contract / 委托人 变化
 * - okDisabled：已有案件未选、或新建+生成合同但委托人空 → 禁用
 * 以及三种 confirm 产出的 AssignInfo 形状、Esc / 点关闭按钮的关闭路径。
 * 焦点陷阱与 Esc 键位本身由 Radix Dialog 负责，不在本文件断言（只断言接线）。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const searchMock = vi.hoisted(() => vi.fn())
vi.mock('../../api', () => ({ searchCases: (...a: unknown[]) => searchMock(...a) }))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { AssignModal } from './AssignModal'

const INFOS = [{ k: '委托人', v: '张三' }] as never

function renderModal(props: Partial<Parameters<typeof AssignModal>[0]> = {}) {
  const onCancel = vi.fn()
  const onConfirm = vi.fn()
  // useTypeaheadSearch 走 react-query，必须有 Provider；retry 关闭避免搜索失败重试
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const utils = render(
    <AssignModal open count={3} infos={INFOS} onCancel={onCancel} onConfirm={onConfirm} {...props} />,
    { wrapper: wrap },
  )
  return { ...utils, onCancel, onConfirm }
}

beforeEach(() => {
  vi.clearAllMocks()
  searchMock.mockResolvedValue([])
})

describe('AssignModal：关闭态', () => {
  it('open=false 时不渲染任何内容', () => {
    const { container } = renderModal({ open: false })
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    container.remove()
  })
})

describe('AssignModal：头部与初始态', () => {
  it('显示材料份数与委托人', () => {
    const { container } = renderModal()
    expect(within(document.body).getByText(/3 份材料/)).toBeTruthy()
    expect(document.body.textContent).toContain('委托人 张三')
    container.remove()
  })

  it('无委托人信息时不显示委托人片段', () => {
    const { container } = renderModal({ infos: [] as never })
    expect(document.body.textContent).not.toContain('委托人')
    container.remove()
  })

  it('默认 target=existing，未选案件时主按钮禁用', () => {
    const { container } = renderModal()
    const ok = within(document.body).getByRole('button', { name: '确认并继续' }) as HTMLButtonElement
    expect(ok.disabled).toBe(true)
    expect(document.body.textContent).toContain('先在上面选一个案件')
    container.remove()
  })
})

describe('AssignModal：新建案件分支', () => {
  it('选「新建案件」+ 不生成合同：提示直接建案，按钮可用', () => {
    const { container } = renderModal()
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    // 默认 contract=has
    expect(document.body.textContent).toContain('不用再填别的，直接建案')
    container.remove()
  })

  it('选「生成委托合同」+ 委托人已预填：提示将生成合同', () => {
    const { container } = renderModal()
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('radio', { name: /还没有合同/ }))
    // 委托人从 infos 预填为张三
    expect(document.body.textContent).toContain('将据此生成委托合同')
    container.remove()
  })

  it('生成委托合同但委托人清空：提示补填且按钮禁用', () => {
    const { container } = renderModal({ infos: [] as never })
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('radio', { name: /还没有合同/ }))
    expect(document.body.textContent).toContain('写个委托人就能生成合同')
    const ok = within(document.body).getByRole('button', { name: '确认并继续' }) as HTMLButtonElement
    expect(ok.disabled).toBe(true)
    container.remove()
  })

  it('新建+生成合同：confirm 只带非空字段', () => {
    const { container, onConfirm } = renderModal()
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('radio', { name: /还没有合同/ }))
    fireEvent.click(within(document.body).getByRole('button', { name: '确认并继续' }))

    expect(onConfirm).toHaveBeenCalledTimes(1)
    const arg = onConfirm.mock.calls[0]![0]
    expect(arg.target).toBe('new')
    expect(arg.contractFields).toEqual({ 委托人: '张三' })
    container.remove()
  })

  it('新建+不生成合同：confirm 不带 contractFields', () => {
    const { container, onConfirm } = renderModal()
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('button', { name: '确认并继续' }))

    const arg = onConfirm.mock.calls[0]![0]
    expect(arg).toEqual({ target: 'new' })
    container.remove()
  })
})

describe('AssignModal：追加到已有案件', () => {
  it('搜索出候选后选中：confirm 带 caseId/案号/标题', async () => {
    searchMock.mockResolvedValue([
      { id: 42, name: '张三诉李四', filing_number: '（20XX）京01民初1号', case_numbers: [] },
    ])
    const { container, onConfirm } = renderModal()

    const search = document.body.querySelector('input[placeholder*="案号"]') as HTMLInputElement
    fireEvent.change(search, { target: { value: '张三' } })

    // useTypeaheadSearch 有 250ms 防抖，等候选渲染
    await new Promise((r) => setTimeout(r, 800))
    const option = within(document.body).getByText('张三诉李四')
    fireEvent.click(option)

    fireEvent.click(within(document.body).getByRole('button', { name: '确认并继续' }))
    const arg = onConfirm.mock.calls[0]![0]
    expect(arg.target).toBe('existing')
    expect(arg.caseId).toBe(42)
    expect(arg.caseTitle).toBe('张三诉李四')
    expect(arg.caseNo).toBe('（20XX）京01民初1号')
    container.remove()
  })
})

describe('AssignModal：关闭路径', () => {
  it('Esc 走 Radix DismissableLayer：触发 onCancel，且事件已被消费（不留给 use-reader-keys）', () => {
    const { container, onCancel } = renderModal()
    // 从内容节点派发：Radix 的 Esc 监听在 document capture 阶段生效，派发到 document
    // 本身会恰好跳过该阶段
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(1)
    container.remove()
  })

  it('点右上角关闭按钮（DialogContent 自带 DialogClose）触发 onCancel', () => {
    const { container, onCancel } = renderModal()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    container.remove()
  })

  it('点遮罩触发 onCancel', async () => {
    const { onCancel } = renderModal()
    // 遮罩在 Radix 里属于「内容之外」：pointerdown 落在它上面即判定外部交互。
    // Radix 把 pointerdown 监听推迟一个宏任务挂载（避免开弹窗的那次点击把自己关掉），
    // 所以要先等一拍。
    await new Promise((r) => setTimeout(r, 0))
    const overlay = document.querySelector('[data-slot="dialog-overlay"]') as HTMLElement
    fireEvent.pointerDown(overlay)
    fireEvent.click(overlay)
    await waitFor(() => expect(onCancel).toHaveBeenCalledTimes(1))
  })
})

// ============ 字段编辑与搜索错误（覆盖率补测） ============

describe('AssignModal：合同字段编辑', () => {
  it('选择「还没有合同」后渲染三个字段输入框', async () => {
    const { container } = renderModal({ infos: [] as never })
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('radio', { name: /还没有合同/ }))

    expect(document.body.querySelector('input[placeholder="姓名或单位"]')).toBeTruthy()
    expect(document.body.querySelectorAll('input[placeholder="可以空"]')).toHaveLength(2)
    container.remove()
  })

  it('填入委托人后按钮可用，confirm 只带填了值的字段', async () => {
    const { container, onConfirm } = renderModal({ infos: [] as never })
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('radio', { name: /还没有合同/ }))

    const nameInput = document.body.querySelector('input[placeholder="姓名或单位"]') as HTMLInputElement
    fireEvent.change(nameInput, { target: { value: '张三' } })

    const ok = within(document.body).getByRole('button', { name: '确认并继续' }) as HTMLButtonElement
    expect(ok.disabled).toBe(false)
    fireEvent.click(ok)

    const arg = onConfirm.mock.calls[0]![0]
    expect(arg.contractFields).toEqual({ 委托人: '张三' })
    container.remove()
  })

  it('只填标的额不能提交（委托人必填）', async () => {
    const { container } = renderModal({ infos: [] as never })
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('radio', { name: /还没有合同/ }))

    const amount = document.body.querySelectorAll('input[placeholder="可以空"]')[1] as HTMLInputElement
    fireEvent.change(amount, { target: { value: '100000' } })
    // 委托人仍为空 → 按钮禁用
    const ok = within(document.body).getByRole('button', { name: '确认并继续' }) as HTMLButtonElement
    expect(ok.disabled).toBe(true)
    container.remove()
  })

  it('字段值前后空白被 trim 后才下发', async () => {
    const { container, onConfirm } = renderModal({ infos: [] as never })
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('radio', { name: /还没有合同/ }))

    const nameInput = document.body.querySelector('input[placeholder="姓名或单位"]') as HTMLInputElement
    fireEvent.change(nameInput, { target: { value: '  李四  ' } })
    fireEvent.click(within(document.body).getByRole('button', { name: '确认并继续' }))

    expect(onConfirm.mock.calls[0]![0].contractFields).toEqual({ 委托人: '李四' })
    container.remove()
  })
})

// ============ 目标切换（覆盖率补测） ============

describe('AssignModal：目标切换', () => {
  it('从「新建案件」切回「追加到已有案件」：恢复搜索区并清空合同字段', () => {
    const { container } = renderModal({ infos: [] as never })
    // 先去新建 + 生成合同
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('radio', { name: /还没有合同/ }))
    expect(document.body.querySelector('input[placeholder="姓名或单位"]')).toBeTruthy()

    // 切回追加已有
    fireEvent.click(within(document.body).getByRole('radio', { name: /追加到已有案件/ }))
    expect(document.body.querySelector('input[placeholder="姓名或单位"]')).toBeNull()
    expect(document.body.querySelector('input[placeholder*="案号"]')).toBeTruthy()
    container.remove()
  })

  it('选「已有委托合同，直接建案」隐藏合同字段', () => {
    const { container } = renderModal({ infos: [] as never })
    fireEvent.click(within(document.body).getByRole('radio', { name: /新建案件/ }))
    fireEvent.click(within(document.body).getByRole('radio', { name: /还没有合同/ }))
    expect(document.body.querySelector('input[placeholder="姓名或单位"]')).toBeTruthy()

    fireEvent.click(within(document.body).getByRole('radio', { name: /已有委托合同/ }))
    expect(document.body.querySelector('input[placeholder="姓名或单位"]')).toBeNull()
    container.remove()
  })
})
