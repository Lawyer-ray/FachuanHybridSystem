/**
 * G3：material-prep 的判决动作（`ui-actions.ts`）—— 名字在清单里、成功/失败/非法参数
 * 三档分得开，且**只走本 feature 自己的 API**（不直接 fetch）。
 *
 * 为什么整块替掉 `./api/inbox-packs`：真实实现是 ky client + `PUT /inbox/messages/{id}/draft`，
 * node 单测既不该发网络请求，也证不了「执行器到底调了谁」。mock 掉的模块**不会执行**，
 * 所以那个文件里的模块初始化（`createApiClient`）也不会发生。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { PageUiAction, UiToolPorts } from '@/features/copilot/ui-tools/contract'
import { UI_TOOL_BY_NAME } from '@/features/copilot/ui-tools/generated'

import { setPackStatusRemote } from './api/inbox-packs'
import {
  judgeMaterialPack,
  PACK_STATUS_CHANGED_EVENT,
  PACK_JUDGE_LABEL,
  uiActions,
} from './ui-actions'

vi.mock('./api/inbox-packs', () => ({ setPackStatusRemote: vi.fn() }))

/** 端口桩：判决动作只用 `dispatch`，其余按契约补齐 */
function makePorts(): UiToolPorts {
  return {
    navigate: vi.fn(),
    currentPath: vi.fn(() => '/material-prep'),
    toast: vi.fn(),
    dispatch: vi.fn(),
    openCopilot: vi.fn(),
  }
}

/** 约定文件里的那一条；缺了就在这炸，不让每条用例各自 `find` 一遍 */
function judgeAction(): PageUiAction {
  const found = uiActions.find((entry) => entry.action === 'ui_material_prep_judge')
  if (found === undefined) throw new Error('ui-actions.ts 没有声明 ui_material_prep_judge')
  return found
}

beforeEach(() => {
  vi.mocked(setPackStatusRemote).mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

/**
 * G3③：执行器不许自己发请求。这个 spy 只要被调一次，就说明有人绕过了 feature 的 api 层
 * （`./api/inbox-packs`）——那时鉴权、401 刷新、错误分类全部失效。
 */
function spyOnFetch() {
  return vi.spyOn(globalThis, 'fetch')
}

describe('动作名与清单对齐（闭集的收集期那一半）', () => {
  it('ui_material_prep_judge 在后端清单的生成物里', () => {
    expect(Object.hasOwn(UI_TOOL_BY_NAME, 'ui_material_prep_judge')).toBe(true)
    expect(judgeAction().action).toBe('ui_material_prep_judge')
  })

  it('uiActions 里每个动作名都在清单里（前端不能实现模型永远不会调的动作）', () => {
    for (const entry of uiActions) {
      expect(Object.hasOwn(UI_TOOL_BY_NAME, entry.action), `清单外动作：${entry.action}`).toBe(true)
    }
  })
})

describe('judgeMaterialPack：写库与失败分类', () => {
  it('成功 → ok + 可读 detail，且调的是本 feature 的 setPackStatusRemote', async () => {
    vi.mocked(setPackStatusRemote).mockResolvedValue(undefined)
    const fetchSpy = spyOnFetch()

    const outcome = await judgeMaterialPack({ packId: 812, target: 'done' })

    expect(outcome).toEqual({ ok: true, detail: `材料包 812 已判为${PACK_JUDGE_LABEL.done}` })
    expect(setPackStatusRemote).toHaveBeenCalledWith(812, 'done')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('api 抛异常 → executor_error（不许静默吞掉，也不许当成参数错误）', async () => {
    vi.mocked(setPackStatusRemote).mockRejectedValue(new Error('后端 500'))

    const outcome = await judgeMaterialPack({ packId: 812, target: 'filed' })

    expect(outcome).toMatchObject({ ok: false, code: 'executor_error' })
  })

  it('非法参数 → invalid_args，且一次库都没写', async () => {
    const fetchSpy = spyOnFetch()
    const bad: Record<string, unknown>[] = [
      { target: 'done' }, // 缺 packId
      { packId: '812', target: 'done' }, // packId 是字符串（JSON 里 id 常见这么来）
      { packId: 812, target: 'archived' }, // target 不在枚举里
    ]

    for (const args of bad) {
      const outcome = await judgeMaterialPack(args)
      expect(outcome, `应判 invalid_args：${JSON.stringify(args)}`).toMatchObject({
        ok: false,
        code: 'invalid_args',
      })
    }
    expect(setPackStatusRemote).not.toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('uiActions 的 execute：广播只在真的改成功时发生', () => {
  it('成功 → dispatch 带 packId 与终态（页面据此重拉列表 + toast）', async () => {
    vi.mocked(setPackStatusRemote).mockResolvedValue(undefined)
    const ports = makePorts()

    const outcome = await judgeAction().execute({ packId: 812, target: 'done' }, ports)

    expect(outcome).toMatchObject({ ok: true })
    expect(ports.dispatch).toHaveBeenCalledWith(PACK_STATUS_CHANGED_EVENT, {
      packId: 812,
      status: 'done',
    })
  })

  it('写库失败 → 不广播（否则页面白拉一次列表，还弹出「已改」的 toast）', async () => {
    vi.mocked(setPackStatusRemote).mockRejectedValue(new Error('后端 500'))
    const ports = makePorts()

    const outcome = await judgeAction().execute({ packId: 812, target: 'done' }, ports)

    expect(outcome).toMatchObject({ ok: false, code: 'executor_error' })
    expect(ports.dispatch).not.toHaveBeenCalled()
  })

  it('参数形状不对 → invalid_args 且不广播（挂起队列那一路 args 会过一轮 JSON）', async () => {
    const ports = makePorts()

    const outcome = await judgeAction().execute({ packId: 812 }, ports)

    expect(outcome).toMatchObject({ ok: false, code: 'invalid_args' })
    expect(ports.dispatch).not.toHaveBeenCalled()
    expect(setPackStatusRemote).not.toHaveBeenCalled()
  })
})
