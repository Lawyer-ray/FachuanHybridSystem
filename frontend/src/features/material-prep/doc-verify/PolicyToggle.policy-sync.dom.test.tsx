// @vitest-environment jsdom
/**
 * 「回传后核对内容」勾选框在**选中既有案件**时的服务端同步（jsdom）。
 *
 * 这条路径修的是「界面说了一句它没有证据的话」：值只来自模块级偏好时，同事在服务端
 * 关掉某案的核对，弹窗里照样打着勾——客户回传时却什么也不核，而且没有任何报错。
 * 所以锁五件事：
 *
 * 1. 勾选值以服务端为准（服务端关着 → 未勾，哪怕偏好勾着；四类只开一部分也算未勾）；
 * 2. 读服务端值期间禁点（拿偏好默认值去写库会悄悄改掉同事做的设置）；
 * 3. 切换先乐观生效，请求载荷是 `{ case_id, enabled, doc_types: [] }`；
 * 4. 写失败回滚到**服务端值**（不是上一个 props）并 toast「核对设置未保存」；
 * 5. 没有案件（新建案件）照旧只走偏好，一个请求都不发。
 *
 * mock 的是 `@/lib/api` 的 `createApiClient`（同 `PendingRuns.dom.test.tsx`）：断言
 * 的是真正发出去的请求，URL、查询参数与载荷都过一遍。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const kyMock = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ createApiClient: () => kyMock }))

const toastMock = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: toastMock }))

import type { PolicyOut } from './api'
import { PolicyToggle } from './PolicyToggle'

/** ky 的 `get/put` 返回可 await 且带 `.json()` 的 ResponsePromise，桩只需 `.json()`。 */
function jsonOf<T>(data: T) {
  return { json: async () => data }
}

/** 失败路径：`./api` 拿到 `.json()` 才拒绝，等价于 ky 在取响应体时炸掉。 */
function jsonFailed(error: unknown) {
  return { json: () => Promise.reject(error as Error) }
}

/** 后端 `policy_store.effective_items` 的口径：四类高风险文书逐条给实际值 + 代码默认。 */
function policyOf(enabled: boolean, caseId = 7): PolicyOut {
  return {
    case_id: caseId,
    items: ['起诉状', '授权委托书', '送达地址确认书', '退费账户确认书'].map((docType) => ({
      doc_type: docType,
      enabled,
      default: true,
    })),
  }
}

function renderToggle(props: {
  caseId?: number
  checked: boolean
  onChange?: (next: boolean) => void
}) {
  const onChange = props.onChange ?? vi.fn()
  // 策略查询走 react-query，必须有 Provider；retry 关闭避免失败重试拖慢用例
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const utils = render(
    <PolicyToggle caseId={props.caseId} checked={props.checked} onChange={onChange} />,
    { wrapper: wrap },
  )
  const box = within(document.body).getByRole('checkbox', {
    name: /回传后核对内容/,
  }) as HTMLInputElement
  return { ...utils, box, onChange }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PolicyToggle：选中既有案件后以服务端策略为准', () => {
  it('服务端关着：勾选显示未勾（哪怕模块偏好勾着），且按该案 id 读策略', async () => {
    kyMock.get.mockReturnValue(jsonOf(policyOf(false)))
    const { container, box } = renderToggle({ caseId: 7, checked: true })

    await waitFor(() => expect(box.checked).toBe(false))
    expect(kyMock.get).toHaveBeenCalledWith(
      'policy',
      expect.objectContaining({ searchParams: { case_id: 7 } }),
    )
    container.remove()
  })

  it('四类只开了一部分：显示未勾（勾选框代表四类一起核，点上是四类一起开）', async () => {
    const mixed = policyOf(true)
    mixed.items[2] = { ...mixed.items[2]!, enabled: false }
    kyMock.get.mockReturnValue(jsonOf(mixed))
    const { container, box } = renderToggle({ caseId: 7, checked: true })

    await waitFor(() => expect(box.checked).toBe(false))
    container.remove()
  })

  it('读服务端值期间禁点：不发 PUT（不能拿偏好默认值去写库）', () => {
    // 永不 resolve：模拟「还在读」
    kyMock.get.mockReturnValue({ json: () => new Promise<never>(() => {}) })
    const { container, box } = renderToggle({ caseId: 7, checked: true })

    expect(box.disabled).toBe(true)
    fireEvent.click(box)
    expect(kyMock.put).not.toHaveBeenCalled()
    container.remove()
  })

  it('切换：先乐观勾上，PUT 载荷带该案 id 与全部高风险类，成功后仍为勾', async () => {
    kyMock.get.mockReturnValue(jsonOf(policyOf(false)))
    let resolvePut: (data: PolicyOut) => void = () => {}
    kyMock.put.mockReturnValue({
      json: () =>
        new Promise<PolicyOut>((resolve) => {
          resolvePut = resolve
        }),
    })
    const { container, box, onChange } = renderToggle({ caseId: 7, checked: true })
    await waitFor(() => expect(box.checked).toBe(false))

    fireEvent.click(box)

    // 不等往返就跟着手走：否则每次点勾都要等一次网络、还会闪回旧值
    expect(box.checked).toBe(true)
    // 模块级偏好照旧更新（下次开弹窗按它，新建案件也读它）
    expect(onChange).toHaveBeenCalledWith(true)
    await waitFor(() => expect(kyMock.put).toHaveBeenCalledTimes(1))
    expect(kyMock.put).toHaveBeenCalledWith(
      'policy',
      expect.objectContaining({ json: { case_id: 7, enabled: true, doc_types: [] } }),
    )

    await act(async () => {
      resolvePut(policyOf(true))
    })
    expect(box.checked).toBe(true)
    expect(box.disabled).toBe(false)
    container.remove()
  })

  it('写失败：回滚到服务端值（不是偏好），并 toast「核对设置未保存」', async () => {
    kyMock.get.mockReturnValue(jsonOf(policyOf(true)))
    let rejectPut: (error: unknown) => void = () => {}
    kyMock.put.mockReturnValue({
      json: () =>
        new Promise<PolicyOut>((_resolve, reject) => {
          rejectPut = reject
        }),
    })
    // 偏好是关、服务端是开：点一下关掉。失败后必须回到服务端的「开」，而不是偏好的「关」
    const { container, box } = renderToggle({ caseId: 7, checked: false })
    await waitFor(() => expect(box.checked).toBe(true))

    fireEvent.click(box)
    expect(box.checked).toBe(false) // 乐观：先按律师点的走
    await waitFor(() => expect(kyMock.put).toHaveBeenCalledTimes(1))

    await act(async () => {
      rejectPut({ name: 'HTTPError', data: { message: '策略服务不可用' } })
    })

    expect(box.checked).toBe(true)
    expect(toastMock.error).toHaveBeenCalledWith('核对设置未保存：策略服务不可用')
    container.remove()
  })

  it('服务端值读不到：退回偏好并就地说明（不假装知道本案设置）', async () => {
    kyMock.get.mockReturnValue(jsonFailed(new Error('网络断了')))
    const { container, box } = renderToggle({ caseId: 7, checked: true })

    await waitFor(() => expect(box.disabled).toBe(false))
    expect(box.checked).toBe(true)
    expect(document.body.textContent).toContain('本案核对设置读取失败')
    container.remove()
  })
})

describe('PolicyToggle：还没选案件时仍走偏好', () => {
  it('一个请求都不发：勾选来自 props，切换只回调偏好', () => {
    const { container, box, onChange } = renderToggle({ checked: false })

    expect(kyMock.get).not.toHaveBeenCalled()
    fireEvent.click(box)
    expect(onChange).toHaveBeenCalledWith(true)
    expect(kyMock.put).not.toHaveBeenCalled()
    // 受控：等 props 改，组件自己不翻转
    expect(box.checked).toBe(false)
    container.remove()
  })
})
