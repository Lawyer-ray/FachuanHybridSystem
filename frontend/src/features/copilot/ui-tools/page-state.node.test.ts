/**
 * `availableActionsForPath`（快照里的 `available_actions` 从哪来）+ 注册表把这份清单带进读取结果。
 *
 * 钉死的四件事，每件都有过对应的失败形态：
 * 1. **本页动作排在全局动作之前**：模型顺序读清单，两个面板级动作挤到前面就会把页面专属动作
 *    顶到截断线以下——表现为「AI 说它不会操作这一页」；
 * 2. **段比较**：`/material-prep-x` 不是 `/material-prep` 的子页，把动作算给它等于让模型在
 *    错页上调本页动作；
 * 3. **≤10 且无重复**：`MAX_AVAILABLE_ACTIONS` 与后端同一上限，前端超发只是让后端白截一次；
 * 4. **页面没声明状态时不给动作名**：那时的清单只能是猜的，模型会照着它调不存在的动作。
 *
 * node 环境（本目录默认）：`currentRoute()` 是空串，「当前地址」只能由入参给——这正是把
 * `availableActionsForPath(pathname)` 做成**纯函数**的收益，判定逻辑不必挂在浏览器上。
 */

import { afterEach, describe, expect, it } from 'vitest'

import { UI_TOOL_SPECS } from './generated'
import {
  availableActionsForPath,
  MAX_AVAILABLE_ACTIONS,
  readPageState,
  registerPageState,
  subscribePageStateReads,
  unregisterPageState,
} from './page-state'

/** 全局动作（`route: null` = 任何页面都能做），按清单顺序 */
const GLOBAL_ACTIONS = UI_TOOL_SPECS.filter((spec) => spec.route === null).map((spec) => spec.name)
/** 落在 `/material-prep` 这一页上的动作，按清单顺序 */
const MATERIAL_PREP_ACTIONS = UI_TOOL_SPECS.filter((spec) => spec.route === '/material-prep').map(
  (spec) => spec.name,
)

/** ④ 注册的 provider：每个用例自己摘干净，免得上一条的状态被下一条读到 */
let registered: (() => Record<string, unknown>) | null = null

afterEach(() => {
  if (registered !== null) unregisterPageState('x', registered)
  registered = null
})

describe('availableActionsForPath：本页动作在前、全局动作在后', () => {
  it('/material-prep 上先给本页动作，再给全局动作，别的页的动作不出现', () => {
    const names = availableActionsForPath('/material-prep')

    // 字面量再断言一次：只靠从生成物推出的期望值，清单被清空时这条测试会「自动通过」
    expect(names).toContain('ui_material_prep_set_stage')
    expect(names).toEqual([...MATERIAL_PREP_ACTIONS, ...GLOBAL_ACTIONS])
    expect(names.slice(0, MATERIAL_PREP_ACTIONS.length)).toEqual(MATERIAL_PREP_ACTIONS)
  })

  it('query 自己剥掉：/material-prep?stage=todo 与 /material-prep 是同一份清单', () => {
    expect(availableActionsForPath('/material-prep?stage=todo')).toEqual(availableActionsForPath('/material-prep'))
  })

  it('子路径算在本页上（/material-prep/393 与列表页共用同一个组件）', () => {
    expect(availableActionsForPath('/material-prep/393')).toEqual(availableActionsForPath('/material-prep'))
  })

  it('按段比：/material-prep-x 不算在 /material-prep 上，只回全局动作', () => {
    expect(availableActionsForPath('/material-prep-x')).toEqual(GLOBAL_ACTIONS)
  })

  it('/ 上只有全局动作（根路径不属于任何业务页）', () => {
    const names = availableActionsForPath('/')

    expect(names).toEqual(GLOBAL_ACTIONS)
    expect(names).not.toContain('ui_material_prep_set_stage')
  })
})

describe('availableActionsForPath：上限与去重（跨端契约）', () => {
  it(`上限常量与后端一致（${MAX_AVAILABLE_ACTIONS}），任何地址都不超发`, () => {
    expect(MAX_AVAILABLE_ACTIONS).toBe(10)
    for (const pathname of ['/', '/material-prep', '/material-prep?stage=done', '/material-prep-x', '', '/projects/393']) {
      const names = availableActionsForPath(pathname)
      expect(names.length).toBeLessThanOrEqual(MAX_AVAILABLE_ACTIONS)
      expect(new Set(names).size).toBe(names.length)
    }
  })
})

describe('readPageState：把动作清单一起带出来', () => {
  it('有页面声明时，availableActions 是数组且含全局动作（node 里当前地址是空串）', () => {
    const provider = (): Record<string, unknown> => ({ stage: 'todo' })
    registered = provider
    registerPageState('x', provider)

    const read = readPageState('x')

    expect(read).not.toBeNull()
    expect(Array.isArray(read?.availableActions)).toBe(true)
    // 空串地址 = 不属于任何业务页 → 只剩全局动作（与 availableActionsForPath('') 同源）
    expect(read?.availableActions).toEqual(availableActionsForPath(''))
    expect(read?.availableActions).toEqual(GLOBAL_ACTIONS)
  })

  it('页面没声明状态时仍是 null，且通知里给的是空清单（不按当前地址编一份猜的动作表）', () => {
    const answers: { state: unknown; availableActions: string[] }[] = []
    const off = subscribePageStateReads((answer) => answers.push(answer))

    expect(readPageState('never-registered')).toBeNull()
    off()

    expect(answers).toHaveLength(1)
    expect(answers[0]?.state).toBeNull()
    expect(answers[0]?.availableActions).toEqual([])
  })
})
