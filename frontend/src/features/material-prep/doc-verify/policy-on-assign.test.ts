/**
 * 归案成功 → 把「回传后核对内容」的策略写到案件上（node 环境）。
 *
 * 为什么这条接线值得单测：它是勾选框**唯一**的落库路径。勾了却没写库，界面照样
 * 打勾、客户回传后却什么也不核——这种「看起来生效」的失效没有任何报错。
 *
 * mock 的是 `@/lib/api` 的 `createApiClient`（不是 `./api`），所以要断言的正是
 * 真正发出去的请求：`PUT policy` 带哪个 `case_id`、`enabled` 跟不跟勾选走。
 * 归案接口本身用桩（真建案要数据库）。
 *
 * 文件放在 doc-verify 而不是 reader 下：被测行为是**核对策略落库**，读代码的人
 * 从功能名能找到它（`use-assign-launch` 的验收在 `reader/use-assign-launch.test.ts`）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(),
    warning: vi.fn(),
  }),
}))

const assignApi = vi.hoisted(() => ({
  assignPack: vi.fn(),
  fetchAttachmentBytes: vi.fn(),
  archiveSplitToCaseFolder: vi.fn(),
}))
vi.mock('../api', () => assignApi)

const kyMock = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ createApiClient: () => kyMock }))

import type { DraftState } from '../types'
import {
  isVerifyAfterReturnEnabled,
  setVerifyAfterReturnEnabled,
  useAssignLaunch,
} from '../components/reader/use-assign-launch'

/** 一份能过「单源连续」校验的最小草稿 */
function draft(): DraftState {
  return {
    mats: [],
    infos: [],
    segs: [
      { id: 's1', t: '起诉状', fn: 'a.pdf', refs: [{ mi: 0, p: 1 }], manual: false },
    ],
  } as DraftState
}

/** 本 hook 不读 React 状态，直接调用即可（同 `reader/use-assign-launch.test.ts` 的理由） */
function useSetup() {
  const deps = {
    draft: draft(),
    messageId: 77,
    navigate: vi.fn(),
    setAssignOpen: vi.fn(),
    setAssign: vi.fn(),
    close: vi.fn(),
    setLaunchFile: vi.fn(),
  }
  return { deps, hook: useAssignLaunch(deps) }
}

const POLICY_OUT = { case_id: 42, items: [] }

beforeEach(() => {
  vi.clearAllMocks()
  assignApi.assignPack.mockResolvedValue({
    caseId: 42,
    caseName: '张某诉某公司',
    contractId: null,
    boundCount: 1,
    unsplitCount: 0,
  })
  assignApi.archiveSplitToCaseFolder.mockResolvedValue({})
  kyMock.put.mockReturnValue({ json: async () => POLICY_OUT })
  setVerifyAfterReturnEnabled(true)
})

/** fire-and-forget：等一拍让那次 PUT 真正发出去 */
async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

describe('归案成功 → 核对策略落库', () => {
  it('勾着：按归案返回的 case id 写 enabled=true（改全部高风险类）', async () => {
    const { hook } = useSetup()

    await hook.onAssignConfirm({ target: 'existing', caseId: 42 })
    await flush()

    expect(kyMock.put).toHaveBeenCalledTimes(1)
    expect(kyMock.put).toHaveBeenCalledWith(
      'policy',
      expect.objectContaining({ json: { case_id: 42, enabled: true, doc_types: [] } }),
    )
  })

  it('没勾：enabled=false（关掉的是这个案子的策略，不是全局偏好丢失）', async () => {
    setVerifyAfterReturnEnabled(false)
    const { hook } = useSetup()

    await hook.onAssignConfirm({ target: 'existing', caseId: 42 })
    await flush()

    expect(kyMock.put).toHaveBeenCalledWith(
      'policy',
      expect.objectContaining({ json: { case_id: 42, enabled: false, doc_types: [] } }),
    )
  })

  it('策略没存上不影响归案：归案照常跳转，失败只落日志（不弹「归案失败」）', async () => {
    kyMock.put.mockReturnValue({ json: () => Promise.reject(new Error('500')) })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { deps, hook } = useSetup()

    await hook.onAssignConfirm({ target: 'existing', caseId: 42 })
    await flush()

    expect(kyMock.put).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('核对策略落库失败'), expect.anything())
    expect(deps.navigate).toHaveBeenCalledWith('/bank-litigation/42')
    warn.mockRestore()
  })

  it('归案失败时一个字都不写（不能拿猜的 case id 去改策略）', async () => {
    assignApi.assignPack.mockRejectedValue({ name: 'HTTPError', data: { message: '材料包已删除' } })
    const { hook } = useSetup()

    await hook.onAssignConfirm({ target: 'existing', caseId: 42 })
    await flush()

    expect(kyMock.put).not.toHaveBeenCalled()
  })

  it('偏好是模块级的：关掉之后重新挂载的 hook 仍读到「关」（弹窗重开不该弹回来）', () => {
    setVerifyAfterReturnEnabled(false)

    // 新挂载一个 hook 实例（弹窗关掉再打开）——模块级变量不该被重置
    useSetup()

    expect(isVerifyAfterReturnEnabled()).toBe(false)
  })
})
