import { describe, expect, it, vi } from 'vitest'

import { UI_TOOL_BY_NAME, UI_TOOL_SPECS } from './generated'
import type { UiToolName } from './generated'
import { resolveExecutor, resolveSpec, runUiTool, UI_EXECUTORS, validateArgs } from './registry'
import { MATERIAL_PREP_STAGES } from './routes'
import type { UiToolPorts } from './types'

/** 端口桩：默认全是 spy，单个用例按需覆盖 */
function makePorts(overrides: Partial<UiToolPorts> = {}): UiToolPorts {
  return {
    navigate: vi.fn(),
    currentPath: vi.fn(() => '/material-prep'),
    toast: vi.fn(),
    dispatch: vi.fn(),
    openCopilot: vi.fn(),
    ...overrides,
  }
}

function request(action: string, args: Record<string, unknown> = {}) {
  return { callId: 'call-1', action, args, route: null }
}

/** 每条 schema 至少一个必被拒的样例（08 §10 的 G2 门禁：防「schema 写错但没人试过」） */
const INVALID_SAMPLES: Record<UiToolName, unknown> = {
  ui_navigate: {}, // 缺必填 path
  ui_copilot_open: { origin: 'invoice' }, // origin 不在枚举里
  ui_material_prep_set_stage: { stage: 'archived' }, // stage 不在枚举里
  ui_material_prep_judge: { packId: 812, target: 'archived' }, // target 只能 done/filed
}

/** 每条 schema 至少一个合法样例（守卫不能把正常参数也拒了） */
const VALID_SAMPLES: Record<UiToolName, unknown> = {
  ui_navigate: { path: '/material-prep?stage=todo' },
  ui_copilot_open: {},
  ui_material_prep_set_stage: { stage: 'done' },
  ui_material_prep_judge: { packId: 812, target: 'done' },
}

describe('双端完备：清单与执行器是同一组名字', () => {
  // 这条是**完备性的唯一门禁**（`UI_EXECUTORS` 放宽成 Partial 之后，编译期不再保证齐全）：
  // 它同时覆盖内置表与页面声明表（`features/*/ui-actions.ts` → discover），任何一边漏了
  // 都会在这里指名道姓地红。
  it('UI_TOOL_SPECS 的每个名字都有执行器', () => {
    for (const spec of UI_TOOL_SPECS) {
      expect(resolveExecutor(spec.name), `缺执行器：${spec.name}`).not.toBeNull()
    }
  })

  it('内置执行器表里没有清单之外的名字', () => {
    // 只断言「⊆ 清单」：内置表不必覆盖全部动作（页面自实现的那条不在这里），
    // 但多写一个清单外的名字就是「实现了一个模型永远不会调的动作」。
    const specNames = UI_TOOL_SPECS.map((spec) => spec.name)
    for (const name of Object.keys(UI_EXECUTORS)) {
      expect(specNames, `内置表里出现了清单外的动作：${name}`).toContain(name)
    }
  })

  it('页面自实现的动作不进内置表（judge 归 material-prep，见 features/material-prep/ui-actions.ts）', () => {
    expect(Object.hasOwn(UI_EXECUTORS, 'ui_material_prep_judge')).toBe(false)
    expect(resolveExecutor('ui_material_prep_judge')).not.toBeNull()
  })

  it('UI_TOOL_BY_NAME 与 UI_TOOL_SPECS 同源', () => {
    for (const spec of UI_TOOL_SPECS) {
      expect(UI_TOOL_BY_NAME[spec.name]).toBe(spec)
    }
  })

  it('未知名字既没有规格也没有执行器（版本漂移要被判成 unknown_action，而不是运行期 TypeError）', () => {
    expect(resolveSpec('ui_open_everything')).toBeNull()
    expect(resolveExecutor('ui_open_everything')).toBeNull()
  })

  it('stage 枚举与 routes.ts 的四阶段一致（清单 / 前端 / 材料预处理页三处不许各写一套）', () => {
    expect(UI_TOOL_BY_NAME.ui_material_prep_set_stage.argsSchema).toMatchObject({
      properties: { stage: { enum: [...MATERIAL_PREP_STAGES] } },
    })
  })

  it('ui_copilot_open 的业务上下文三字段全部可选（required 必须为空，否则「纯打开」变成非法调用）', () => {
    // 后端把没传的可选参数补成 None 后已在工具体里过滤掉（register.py），
    // 这里守的是**清单**这一侧：谁把 required 写成三者，最常见的「打开面板」当场失效。
    expect(UI_TOOL_BY_NAME.ui_copilot_open.argsSchema).toMatchObject({
      additionalProperties: false,
      properties: {
        origin: { enum: ['case', 'contract'], type: 'string' },
        refId: { type: 'integer' },
        title: { type: 'string' },
      },
      required: [],
    })
  })
})

describe('validateArgs：手写守卫', () => {
  it('每条 schema 的合法样例都放行', () => {
    for (const spec of UI_TOOL_SPECS) {
      expect(validateArgs(spec, VALID_SAMPLES[spec.name]), `误拒：${spec.name}`).toBe(true)
    }
  })

  it('每条 schema 的非法样例都被拒', () => {
    for (const spec of UI_TOOL_SPECS) {
      expect(validateArgs(spec, INVALID_SAMPLES[spec.name]), `漏放：${spec.name}`).toBe(false)
    }
  })

  it('additionalProperties=false 时多余参数被拒', () => {
    expect(validateArgs(UI_TOOL_BY_NAME.ui_navigate, { path: '/assistant', dry_run: true })).toBe(false)
  })

  it('非对象参数被拒（数组、null、字符串都不算参数对象）', () => {
    for (const raw of [null, undefined, '/assistant', ['/assistant'], 7]) {
      expect(validateArgs(UI_TOOL_BY_NAME.ui_navigate, raw)).toBe(false)
    }
  })

  it('布尔值不算 integer（`refId: true` 不能混过去）', () => {
    expect(
      validateArgs(UI_TOOL_BY_NAME.ui_copilot_open, { origin: 'case', refId: true, title: '张三' }),
    ).toBe(false)
  })
})

describe('runUiTool：错误分类', () => {
  it('未知动作 → unknown_action（且不执行任何端口调用）', async () => {
    const ports = makePorts()
    const outcome = await runUiTool(request('ui_delete_everything'), ports)
    expect(outcome).toMatchObject({ ok: false, code: 'unknown_action' })
    expect(ports.navigate).not.toHaveBeenCalled()
  })

  it('缺必填参数 → invalid_args', async () => {
    const outcome = await runUiTool(request('ui_navigate'), makePorts())
    expect(outcome).toMatchObject({ ok: false, code: 'invalid_args' })
  })

  it('错枚举 → invalid_args', async () => {
    const outcome = await runUiTool(request('ui_material_prep_set_stage', { stage: 'archived' }), makePorts())
    expect(outcome).toMatchObject({ ok: false, code: 'invalid_args' })
  })

  it('恶意路径 → route_unreachable，且真的没有跳转', async () => {
    const ports = makePorts()
    const outcome = await runUiTool(request('ui_navigate', { path: 'javascript:alert(1)' }), ports)
    expect(outcome).toMatchObject({ ok: false, code: 'route_unreachable' })
    expect(ports.navigate).not.toHaveBeenCalled()
  })

  it('执行器抛异常 → executor_error（不许静默吞掉）', async () => {
    const ports = makePorts({
      navigate: vi.fn(() => {
        throw new Error('router 未就绪')
      }),
    })
    const outcome = await runUiTool(request('ui_navigate', { path: '/assistant' }), ports)
    expect(outcome).toMatchObject({ ok: false, code: 'executor_error' })
  })
})

describe('runUiTool：三条 safe 动作的正常路径', () => {
  it('ui_navigate 跳到白名单内的地址', async () => {
    const ports = makePorts()
    const outcome = await runUiTool(request('ui_navigate', { path: '/material-prep?stage=todo' }), ports)
    expect(outcome).toEqual({ ok: true, detail: '/material-prep?stage=todo' })
    expect(ports.navigate).toHaveBeenCalledWith('/material-prep?stage=todo')
  })

  it('ui_copilot_open 带业务上下文时原样透传', async () => {
    const ports = makePorts()
    const context = { origin: 'case' as const, refId: 812, title: '张三诉李四' }
    const outcome = await runUiTool(request('ui_copilot_open', context), ports)
    expect(outcome).toMatchObject({ ok: true })
    expect(ports.openCopilot).toHaveBeenCalledWith(context)
  })

  it('ui_copilot_open 无参数时普通打开（不硬拼一个假的业务上下文）', async () => {
    const ports = makePorts()
    const outcome = await runUiTool(request('ui_copilot_open'), ports)
    expect(outcome).toMatchObject({ ok: true })
    expect(ports.openCopilot).toHaveBeenCalledWith(undefined)
  })

  it('ui_copilot_open 只给了半截上下文时降级为普通打开', async () => {
    const ports = makePorts()
    const outcome = await runUiTool(request('ui_copilot_open', { origin: 'contract', refId: 44 }), ports)
    expect(outcome).toMatchObject({ ok: true })
    expect(ports.openCopilot).toHaveBeenCalledWith(undefined)
  })

  it('ui_material_prep_set_stage 用 replace 切阶段，并保住 ?message=', async () => {
    const ports = makePorts({ currentPath: vi.fn(() => '/material-prep?message=12') })
    const outcome = await runUiTool(request('ui_material_prep_set_stage', { stage: 'todo' }), ports)
    expect(outcome).toMatchObject({ ok: true })
    expect(ports.navigate).toHaveBeenCalledWith('/material-prep?message=12&stage=todo', { replace: true })
  })

  it('ui_material_prep_set_stage 切回收件箱时不写冗余 stage 参数', async () => {
    const ports = makePorts({ currentPath: vi.fn(() => '/material-prep?stage=done') })
    await runUiTool(request('ui_material_prep_set_stage', { stage: 'inbox' }), ports)
    expect(ports.navigate).toHaveBeenCalledWith('/material-prep', { replace: true })
  })
})
