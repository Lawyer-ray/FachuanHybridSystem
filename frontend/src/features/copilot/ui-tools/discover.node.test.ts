/**
 * 页面动作自动发现：合并语义、闭集守卫、以及「覆盖内置执行器也绕不过白名单」。
 *
 * 断言分三层，缺一层这条通道就是「看起来接上了」：
 * 1. **纯逻辑**：`collectExecutors` 对模块表的合并与跳过（直接喂假模块，不碰文件系统）；
 * 2. **真实聚合**：`import.meta.glob` 今天收出来的东西（第一个约定文件已落地，
 *    所以必须能收到 `ui_material_prep_judge`；空表反而是故障）；
 * 3. **端到端一跳**：注入假模块后 `resolveExecutor` / `runUiTool` 真的走到页面实现，
 *    且 `ui_navigate` 的路径白名单**不跟着执行器走**（安全不变式）。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { COLLECTED_PAGE_EXECUTORS, collectExecutors } from './discover'
import { UI_TOOL_BY_NAME, UI_TOOL_SPECS } from './generated'
import { resolveExecutor, runUiTool, setPageExecutors } from './registry'
import type { PageUiAction, UiExecutor, UiToolPorts } from './types'

/** 假模块的路径（glob 的键就是这种形态，文案里要带它） */
const MODULE_A = '/src/features/fake-a/ui-actions.ts'
const MODULE_B = '/src/features/fake-b/ui-actions.ts'

/**
 * 一条假的页面动作。`action` 故意放宽成 `string`：非法动作名正是要测的输入，
 * 而 `PageUiAction['action']` 是闭集（能写出非法名字本身就说明生成物陈旧或手改过）。
 */
function pageAction(action: string, execute: UiExecutor): PageUiAction {
  return { action, execute } as PageUiAction
}

/** 端口桩：默认全是 spy，用例按需覆盖 */
function makePorts(overrides: Partial<UiToolPorts> = {}): UiToolPorts {
  return {
    navigate: vi.fn(),
    currentPath: vi.fn(() => '/'),
    toast: vi.fn(),
    dispatch: vi.fn(),
    openCopilot: vi.fn(),
    ...overrides,
  }
}

afterEach(() => {
  // 还原真实发现表（今天只含页面自实现的那条，与内置表不重叠，因此不会产生覆盖提示），
  // 再撤掉 console 的 spy
  setPageExecutors(COLLECTED_PAGE_EXECUTORS)
  vi.restoreAllMocks()
})

describe('① 真实聚合：仓库当前的 ui-actions.ts', () => {
  it('真的收到了 material-prep 声明的 ui_material_prep_judge（glob 模式没挂错）', () => {
    // 这条是 `UI_EXECUTORS` 放宽成 Partial 之后的**第二条完备性门禁**：
    // 只有 registry 那条时，glob 模式写错也只会红在「缺执行器」，要查半天才知道红在哪一层。
    // 所以这里**不要**改回 `size === 0`——第一个约定文件已经落地，空表才是故障。
    expect(COLLECTED_PAGE_EXECUTORS.has('ui_material_prep_judge')).toBe(true)
    expect(COLLECTED_PAGE_EXECUTORS.size).toBeGreaterThanOrEqual(1)
  })

  it('聚合结果只可能含清单里的动作（闭集在收集期就成立，不靠执行期兜）', () => {
    for (const name of COLLECTED_PAGE_EXECUTORS.keys()) {
      expect(Object.hasOwn(UI_TOOL_BY_NAME, name), `发现表里出现了清单外的动作：${name}`).toBe(true)
    }
  })
})

describe('② 合并语义：多模块聚合 / 清单外动作被忽略并提示', () => {
  it('多个 feature 的动作合进同一张表', () => {
    const stageImpl = vi.fn()
    const navigateImpl = vi.fn()
    const executors = collectExecutors({
      [MODULE_A]: { uiActions: [pageAction('ui_material_prep_set_stage', stageImpl)] },
      [MODULE_B]: { uiActions: [pageAction('ui_navigate', navigateImpl)] },
    })
    expect([...executors.keys()].sort()).toEqual(['ui_material_prep_set_stage', 'ui_navigate'])
    expect(executors.get('ui_navigate')).toBe(navigateImpl)
  })

  it('清单外的动作被忽略，并提示「模型不会调用它」', () => {
    const warn = vi.fn()
    const executors = collectExecutors(
      { [MODULE_B]: { uiActions: [pageAction('ui_delete_everything', vi.fn())] } },
      warn,
    )
    expect(executors.size).toBe(0)
    expect(warn).toHaveBeenCalledTimes(1)
    expect(warn.mock.calls[0]?.[0]).toBe(
      `动作 ui_delete_everything 已在前端实现，但后端 manifest 没声明 → 模型不会调用它（${MODULE_B}）`,
    )
  })

  it('约定文件存在但没导出 uiActions 数组时也出声，而不是静默少一批动作', () => {
    const warn = vi.fn()
    const executors = collectExecutors({ [MODULE_A]: {} }, warn)
    expect(executors.size).toBe(0)
    expect(warn.mock.calls[0]?.[0]).toBe(
      `${MODULE_A} 没有导出 uiActions 数组，已跳过（约定见 docs/harness/frontend/ui-actions.md）`,
    )
  })

  it('同一动作被两个 feature 声明时只留一份（后收集到的胜出）', () => {
    const first = vi.fn()
    const second = vi.fn()
    const executors = collectExecutors({
      [MODULE_A]: { uiActions: [pageAction('ui_material_prep_set_stage', first)] },
      [MODULE_B]: { uiActions: [pageAction('ui_material_prep_set_stage', second)] },
    })
    expect(executors.size).toBe(1)
    expect(executors.get('ui_material_prep_set_stage')).toBe(second)
  })
})

describe('③ 注入假模块后：页面实现优先，但白名单不跟着执行器走', () => {
  it('③a 页面实现覆盖内置执行器 → resolveExecutor 取到页面那份', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const pageImpl = vi.fn(() => ({ ok: true as const, detail: '页面实现' }))
    setPageExecutors(
      collectExecutors({ [MODULE_A]: { uiActions: [pageAction('ui_material_prep_set_stage', pageImpl)] } }),
    )
    expect(resolveExecutor('ui_material_prep_set_stage')).toBe(pageImpl)
  })

  it('③a-2 覆盖内置执行器时收集期就吵一句（文案说明白名单守卫已上提）', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    setPageExecutors(
      collectExecutors(
        { [MODULE_A]: { uiActions: [pageAction('ui_material_prep_set_stage', vi.fn())] } },
        () => {},
      ),
    )
    expect(warn).toHaveBeenCalledWith(
      '页面实现覆盖了内置执行器 ui_material_prep_set_stage；若是 ui_navigate 请确认白名单守卫仍在（现在它在 runUiTool 层，不受覆盖影响）',
    )
  })

  it('③b 覆盖 ui_navigate 也绕不过白名单：先拒，页面执行器一次都没被调用', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const pageImpl = vi.fn(() => ({ ok: true as const }))
    setPageExecutors(collectExecutors({ [MODULE_A]: { uiActions: [pageAction('ui_navigate', pageImpl)] } }))
    const ports = makePorts()

    const outcome = await runUiTool(
      { callId: 'call-1', action: 'ui_navigate', args: { path: 'javascript:alert(1)' }, route: null },
      ports,
    )

    expect(outcome).toMatchObject({ ok: false, code: 'route_unreachable' })
    expect(pageImpl).not.toHaveBeenCalled()
    expect(ports.navigate).not.toHaveBeenCalled()
  })

  it('③b-2 合法路径才交给页面实现（守卫只拦非法路径，不把动作吞掉）', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const pageImpl = vi.fn(() => ({ ok: true as const, detail: '页面自己跳' }))
    setPageExecutors(collectExecutors({ [MODULE_A]: { uiActions: [pageAction('ui_navigate', pageImpl)] } }))
    const ports = makePorts()

    const outcome = await runUiTool(
      { callId: 'call-2', action: 'ui_navigate', args: { path: '/projects' }, route: null },
      ports,
    )

    expect(outcome).toMatchObject({ ok: true, detail: '页面自己跳' })
    expect(pageImpl).toHaveBeenCalledTimes(1)
    // 页面实现自己决定怎么跳；执行层没有替你跳（否则就是两套行为了）
    expect(ports.navigate).not.toHaveBeenCalled()
  })

  it('③c 发现表里的清单外动作既不可解析、也不在结果表里（闭集不被前端单方面放开）', () => {
    const warn = vi.fn()
    setPageExecutors(collectExecutors({ [MODULE_B]: { uiActions: [pageAction('ui_open_everything', vi.fn())] } }, warn))
    expect(resolveExecutor('ui_open_everything')).toBeNull()
    expect(warn).toHaveBeenCalledTimes(1)
  })

  it('清单里的每条动作都能解析到执行器（页面实现 + 内置兜底合起来仍是完备闭集）', () => {
    for (const spec of UI_TOOL_SPECS) {
      expect(resolveExecutor(spec.name), `缺执行器：${spec.name}`).not.toBeNull()
    }
  })
})
