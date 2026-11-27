/**
 * 动作名 → 执行器：前端执行层的**闭集**，以及参数的**第二道**守卫。
 *
 * 两道闸都是「静默失效」的解药：
 * 1. `record<UiToolName, UiExecutor>` 让「清单里有、执行器没有」在编译期就红——
 *    否则模型调完页面毫无反应、日志里连报错都没有（这是本条链路上最贵的故障形态）。
 * 2. 后端已按 `args_schema` 校验过一轮，这里再校验一次：灰度期前端旧、后端新时，
 *    新参数形状会带着旧前端一起跑，此时唯一能拦住的是本地守卫。
 *
 * **不写业务 API 调用**：`confirm` 类动作要真写库时，走 `ports.dispatch` 让目标
 * feature 自己消费（`launch.ts` 的既定模式），执行器不 import 别的 feature 内部——
 * 那会把对方的 chunk 拖进 copilot 的懒加载边界。
 */

import { UI_TOOL_BY_NAME, UI_TOOL_SPECS } from './generated'
import type { UiToolName, UiToolSpec } from './generated'
import { MATERIAL_PREP_STAGES, pathForMaterialPrepStage, pathForNavigate } from './routes'
import type { UiActionRequest, UiExecutor, UiToolOutcome, UiToolPorts } from './types'

/** JSON 对象判定（数组与 null 都不算对象；与后端 schema.py 的口径一致） */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 只校验 `type` / `enum` / `required` / `additionalProperties` —— 与后端
 * `apps/agent/services/ui_action/schema.py` 支持的关键字**逐个对齐**。
 *
 * 多支持一个关键字就多一个漂移点：清单里写了 `pattern` 而这里不认，结果就是
 * 「看起来校验过了」的静默放行，比不校验更危险。要扩就先扩两端。
 */
const TYPE_CHECKS: Record<string, (value: unknown) => boolean> = {
  string: (value) => typeof value === 'string',
  // 布尔值不是数字：不显式挡，`{"stage": true}` 之类会混过 integer/number
  integer: (value) => typeof value === 'number' && Number.isInteger(value),
  number: (value) => typeof value === 'number' && Number.isFinite(value),
  boolean: (value) => typeof value === 'boolean',
  object: isRecord,
  array: Array.isArray,
}

/** 参数是否符合该动作的 schema（`true` = 放行） */
export function validateArgs(spec: UiToolSpec, args: unknown): boolean {
  if (!isRecord(args)) return false
  const schema = spec.argsSchema
  const properties = isRecord(schema.properties) ? schema.properties : {}
  if (schema.additionalProperties === false) {
    for (const key of Object.keys(args)) {
      // 多余参数一律拒：模型自己编出来的字段要么是误解，要么该是另一个动作的参数
      if (!Object.hasOwn(properties, key)) return false
    }
  }
  if (Array.isArray(schema.required)) {
    for (const name of schema.required) {
      if (typeof name === 'string' && !Object.hasOwn(args, name)) return false
    }
  }
  for (const [name, value] of Object.entries(args)) {
    const property = properties[name]
    if (!isRecord(property)) continue
    const check = typeof property.type === 'string' ? TYPE_CHECKS[property.type] : undefined
    if (check && !check(value)) return false
    const allowed = property.enum
    if (Array.isArray(allowed) && !allowed.includes(value)) return false
  }
  return true
}

/** 名字 → 规格；清单里没有的名字返回 `null`（不是抛异常：版本漂移要能被分类） */
export function resolveSpec(name: string): UiToolSpec | null {
  return Object.hasOwn(UI_TOOL_BY_NAME, name) ? UI_TOOL_BY_NAME[name as UiToolName] : null
}

/** 名字 → 执行器；不在闭集里返回 `null` */
export function resolveExecutor(name: string): UiExecutor | null {
  return Object.hasOwn(UI_EXECUTORS, name) ? UI_EXECUTORS[name as UiToolName] : null
}

/**
 * `ui_copilot_open` 的业务上下文：三个字段齐全才认。
 *
 * 缺一个就退回「普通打开」而不是报错：打开面板本身是律师要的那件事，
 * 少个 chip 只是少了上下文；反过来硬拼一个 `{origin:'case', refId:0, title:''}`
 * 会让面板头挂上一条根本不存在的案件——比不挂更糟。
 */
function copilotContext(args: Record<string, unknown>): { origin: 'case' | 'contract'; refId: number; title: string } | null {
  const { origin, refId, title } = args
  if ((origin !== 'case' && origin !== 'contract') || typeof refId !== 'number' || typeof title !== 'string') {
    return null
  }
  return { origin, refId, title }
}

/** 报错文案里的阶段清单：从 routes 的常量拼，不另抄一份字面量 */
const MATERIAL_PREP_STAGE_LIST = MATERIAL_PREP_STAGES.join(' / ')

/**
 * 执行器闭集：`Record<UiToolName, UiExecutor>` 在清单多一条而这里少一条时直接编译红，
 * 这正是「双端完备」在类型系统里能拿到的最强保证。
 */
export const UI_EXECUTORS: Record<UiToolName, UiExecutor> = {
  ui_navigate: (args, ports) => {
    const path = pathForNavigate(args.path)
    if (path === null) {
      return {
        ok: false,
        code: 'route_unreachable',
        message: '跳转被拒：这个地址不在站内白名单里（只接受应用自己的页面路径）',
      }
    }
    ports.navigate(path)
    return { ok: true, detail: path }
  },
  ui_copilot_open: (args, ports) => {
    const context = copilotContext(args)
    ports.openCopilot(context ?? undefined)
    return { ok: true, detail: context ? `已在「${context.title}」上下文中打开助手` : '已打开助手' }
  },
  ui_material_prep_set_stage: (args, ports) => {
    const path = pathForMaterialPrepStage(args.stage, ports.currentPath())
    if (path === null) {
      // 走到这里说明 validateArgs 放过了非法 stage（schema 与本文件不同源）——按参数错误报
      return {
        ok: false,
        code: 'invalid_args',
        message: `切换阶段被拒：stage 只能是 ${MATERIAL_PREP_STAGE_LIST}，收到 ${String(args.stage)}`,
      }
    }
    // replace：切筛选是原地改状态，压进历史栈会让「后退」一步步退回上一个筛选
    ports.navigate(path, { replace: true })
    return { ok: true, detail: path }
  },
}

/**
 * 一次完整的动作执行：解析 → 校验 → 执行 → 兜异常。
 *
 * 放在这里而不是 store：错误码的分类是**执行层知识**（哪个码能重试、哪个码要告警），
 * 而 store 只该管幂等、打断与落态。把分类留在 registry，store 的 `runUiAction`
 * 就只剩「取结果、写 uiToolRuns」两件事。
 */
export async function runUiTool(req: UiActionRequest, ports: UiToolPorts): Promise<UiToolOutcome> {
  const executor = resolveExecutor(req.action)
  const spec = resolveSpec(req.action)
  if (!executor || !spec) {
    // 先发前端、再发后端是灰度铁律；命中这里说明顺序反了，要打点告警而不是猜着执行
    return { ok: false, code: 'unknown_action', message: `前端不认识动作 ${req.action}（前端版本落后于后端）` }
  }
  if (!validateArgs(spec, req.args)) {
    return { ok: false, code: 'invalid_args', message: `动作 ${req.action} 的参数不合法` }
  }
  try {
    return await executor(req.args, ports)
  } catch (error) {
    return {
      ok: false,
      code: 'executor_error',
      message: error instanceof Error ? error.message : String(error),
    }
  }
}

/** 清单里的动作名（测试与治理门禁用；顺序即清单声明序） */
export const UI_TOOL_NAMES: readonly UiToolName[] = UI_TOOL_SPECS.map((spec) => spec.name)
