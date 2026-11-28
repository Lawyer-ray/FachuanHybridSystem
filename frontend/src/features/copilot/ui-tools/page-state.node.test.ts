/**
 * `availableActionsForPath`（快照里的 `available_actions` 从哪来）+ 注册表把这份清单带进读取结果。
 *
 * 钉死的四件事，每件都有过对应的失败形态：
 * 1. **本页动作排在全局动作之前**：模型顺序读清单，两个面板级动作挤到前面就会把页面专属动作
 *    顶到截断线以下——表现为「AI 说它不会操作这一页」；
 * 2. **段比较**：`/material-prep-x` 不是 `/material-prep` 的子页，把动作算给它等于让模型在
 *    错页上调本页动作；
 * 3. **≤10 且无重复**：`MAX_AVAILABLE_ACTIONS` 与后端同一上限，前端超发只是让后端白截一次；
 * 4. **页面没声明状态时不给动作名**：那时的清单只能是猜的，模型会照着它调不存在的动作；
 * 5. **`blockedActions` 跟着页面走**：页面登记了才带出、页面卸载/清掉就不再带（否则模型在
 *    一个已经能做的页面上仍然读「先选一条」，会白问律师一句）；
 * 6. **`privateState` 与 `state` 分两半存**：私有的那一半只进日志、**不混进 `state`**
 *    （混进去就是把律师没提交的草稿交给模型当既成事实）；没登记时是 `{}`，不是 `undefined`。
 *
 * node 环境（本目录默认）：`currentRoute()` 是空串，「当前地址」只能由入参给——这正是把
 * `availableActionsForPath(pathname)` 做成**纯函数**的收益，判定逻辑不必挂在浏览器上。
 */

import { afterEach, describe, expect, it } from 'vitest'

import { UI_TOOL_SPECS } from './generated'
import {
  availableActionsForPath,
  clearPageBlockedActions,
  clearPagePrivateState,
  MAX_AVAILABLE_ACTIONS,
  MAX_BLOCKED_ACTIONS,
  readPageState,
  registerPageState,
  setPageBlockedActions,
  setPagePrivateState,
  subscribePageStateReads,
  unregisterPageState,
} from './page-state'
import type { PageStateAnswer } from './page-state'

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
  // blocked / private 表都是模块级 Map：漏清一条会让下一条用例读到上一条的原因 / 草稿
  clearPageBlockedActions('x')
  clearPageBlockedActions('y')
  clearPagePrivateState('x')
  clearPagePrivateState('y')
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
    const answers: PageStateAnswer[] = []
    const off = subscribePageStateReads((answer) => answers.push(answer))

    expect(readPageState('never-registered')).toBeNull()
    off()

    expect(answers).toHaveLength(1)
    expect(answers[0]?.state).toBeNull()
    expect(answers[0]?.availableActions).toEqual([])
    // 同理：页面都没对上，「做不了什么」也只能算猜
    expect(answers[0]?.blockedActions).toEqual([])
  })
})

/** ② 一份像样的「做不了」声明：名字取自真清单（`ui_material_prep_judge`） */
function blockedJudge(reason = '当前没有选中材料包：先让律师选一条'): { name: string; reason: string } {
  return { name: 'ui_material_prep_judge', reason }
}

describe('blockedActions：页面说「有但此刻做不了」的那份清单', () => {
  it('页面登记了就一并读出来；同一条仍在 availableActions 里（两者不互斥）', () => {
    const provider = (): Record<string, unknown> => ({ selected: null })
    registered = provider
    registerPageState('x', provider)
    setPageBlockedActions('x', [blockedJudge()])

    const read = readPageState('x')

    expect(read?.blockedActions).toEqual([blockedJudge()])
    // 动作清单是按路由静态算的，不知道「选中了哪一条」——同一条两边都在是预期形态
    // （node 里当前地址是空串，所以这里直接问 route 版本；后端/工具描述写明「以 blocked 为准」）
    expect(read?.availableActions).not.toContain('ui_material_prep_judge')
    expect(availableActionsForPath('/material-prep')).toContain('ui_material_prep_judge')
  })

  it('清掉之后不再带（律师选了就不该再报「做不了」）', () => {
    const provider = (): Record<string, unknown> => ({ selected: 812 })
    registered = provider
    registerPageState('x', provider)
    setPageBlockedActions('x', [blockedJudge()])
    expect(readPageState('x')?.blockedActions).toHaveLength(1)

    clearPageBlockedActions('x')

    expect(readPageState('x')?.blockedActions).toEqual([])
  })

  it('按页分开：给 x 登记不影响 y，也不出现在别人的读取结果里', () => {
    const provider = (): Record<string, unknown> => ({ v: 1 })
    registered = provider
    registerPageState('x', provider)
    registerPageState('y', provider)
    setPageBlockedActions('x', [blockedJudge()])

    expect(readPageState('y')?.blockedActions).toEqual([])
    unregisterPageState('y', provider)
  })

  it(`只留前 ${MAX_BLOCKED_ACTIONS} 条（与后端同一上限，两端各截一次）`, () => {
    const provider = (): Record<string, unknown> => ({ v: 1 })
    registered = provider
    registerPageState('x', provider)
    setPageBlockedActions(
      'x',
      Array.from({ length: MAX_BLOCKED_ACTIONS + 2 }, (_, i) => blockedJudge(`原因 ${i}`)),
    )

    const read = readPageState('x')

    expect(MAX_BLOCKED_ACTIONS).toBe(10)
    expect(read?.blockedActions).toHaveLength(MAX_BLOCKED_ACTIONS)
    expect(read?.blockedActions[0]).toEqual(blockedJudge('原因 0'))
  })

  it('页面没声明状态时仍返回 null（语义不变，blocked 不会把 null 变成一份快照）', () => {
    // 只登记 blocked、不登记 provider：注册表里没有这一页
    setPageBlockedActions('never-registered', [blockedJudge()])

    expect(readPageState('never-registered')).toBeNull()
  })
})

describe('privateState：不进模型上下文的那一半（未提交草稿 / 原始 id / 调试字段）', () => {
  it('页面登记了就一并读出来，且**不混进 state**', () => {
    const provider = (): Record<string, unknown> => ({ stage: 'todo' })
    registered = provider
    registerPageState('x', provider)
    setPagePrivateState('x', { openDetail: '/material-prep/571' })

    const read = readPageState('x')

    expect(read?.privateState).toEqual({ openDetail: '/material-prep/571' })
    // 分开存是这条通道存在的全部意义：混进 state 就等于把草稿交给了模型
    expect(read?.state).toEqual({ stage: 'todo' })
  })

  it('清掉之后不再带（上一个实例的私有状态属于上一个实例）', () => {
    const provider = (): Record<string, unknown> => ({ v: 1 })
    registered = provider
    registerPageState('x', provider)
    setPagePrivateState('x', { draftText: '未提交' })
    expect(readPageState('x')?.privateState).toEqual({ draftText: '未提交' })

    clearPagePrivateState('x')

    expect(readPageState('x')?.privateState).toEqual({})
  })

  it('页面没声明状态时通知里是空对象（不是 undefined：调用方不必再判空）', () => {
    const answers: PageStateAnswer[] = []
    const off = subscribePageStateReads((answer) => answers.push(answer))

    expect(readPageState('never-registered')).toBeNull()
    off()

    expect(answers[0]?.state).toBeNull()
    expect(answers[0]?.privateState).toEqual({})
  })

  it('按页分开：给 x 登记不影响 y', () => {
    const provider = (): Record<string, unknown> => ({ v: 1 })
    registered = provider
    registerPageState('x', provider)
    registerPageState('y', provider)
    setPagePrivateState('x', { draftText: '未提交' })

    expect(readPageState('y')?.privateState).toEqual({})
    unregisterPageState('y', provider)
  })
})
