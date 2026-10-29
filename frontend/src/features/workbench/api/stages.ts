/**
 * 专项阶段：`GET/PUT /api/v1/contracts/contracts/{id}/stages` 的前端契约。
 *
 * **为什么阶段要独占一个端点，而不是塞进 ContractOut**：阶段是结构化树（顺序 +
 * 层次 + 验收标准 + 交付物 + 模板绑定），与「代理阶段」那种中文标签数组
 * （`representation_stages`）不是同一件事——后者只够表达「代理了哪些程序」。
 * 阶段会随办案不断被律师改（改名、升降级、加子阶段），单独一条读写端点才能
 * 只提交这一块、不碰合同其余字段（整份合同回写会撞乐观锁，也容易覆盖别人的修改）。
 *
 * **端点尚未上线时的行为**：读失败一律降级成空阶段树，页面用本地 state 跑通
 * UI——律师可以先设计阶段，写回失败时提示「未保存到服务器」，不白屏、不把
 * 404 当页面级错误。
 */

import type { PhaseNode } from '../components/deal-detail/special-phase-tree'
import { normalizeTree } from '../components/deal-detail/special-phase-tree'
import { contractsApi } from './client'

/** 后端契约：一棵阶段树（key 稳定，改名不丢交付物） */
export interface ContractStagesResponse {
  stages: PhaseNode[]
}

/**
 * 后端阶段节点 → 前端 PhaseNode 的适配。
 *
 * **为什么需要这一层**：后端字段叫 `children`（与 `Contract.stages` JSONField 的
 * 存盘形状一致），前端内部叫 `folders`（它同时承载「子阶段」与「该阶段的目录」，
 * 命名在这里更连贯）。两边各自合理，但此前**直接透传**——后端返回的 `children`
 * 被 normalizeTree 当成未知字段丢掉，子阶段静默消失：实测 API 返回
 * `ph_draft.children.length === 2`，页面上却只有 5 个顶层阶段。
 *
 * 同时做交付物字段名对齐：后端 `doc` → 前端 `name`，后端 `ver` → 前端 `version`。
 */
/**
 * 交付物的稳定 id：后端不存（它是渲染期定位用的）。
 * 按 subpath → 文书名 → 序号依次取值，保证同一份文书每轮渲染拿到同一个 id，
 * 点开编辑器、删行都不会认错行。
 */
function stringifyId(...candidates: unknown[]): string {
  for (const c of candidates) {
    if (typeof c === 'string' && c) return c
  }
  return ''
}

function fromBackendNode(p: Record<string, unknown>): Record<string, unknown> {
  const kids = (p.children ?? p.folders) as Record<string, unknown>[] | undefined
  const docs = (p.deliverables ?? []) as Record<string, unknown>[]
  return {
    key: p.key,
    name: p.name,
    acceptance: p.acceptance,
    startDate: p.date ?? p.startDate,
    open: p.open,
    folders: (kids ?? []).map(fromBackendNode),
    deliverables: docs.map((d) => ({
      // id 后端不存（它是渲染期定位用的），按 subpath/名称推一个稳定值
      id: typeof d.id === 'string' ? d.id : stringifyId(d.subpath, d.doc, d.name),
      date: d.date,
      name: d.doc ?? d.name,
      version: d.ver ?? d.version,
      state: d.state,
      subpath: d.subpath,
      planned: d.planned ?? !d.subpath,
    })),
  }
}

/** 前端 PhaseNode → 后端节点（写回时用，与 fromBackendNode 严格互逆） */
function toBackendNode(p: PhaseNode): Record<string, unknown> {
  return {
    key: p.key,
    name: p.name,
    acceptance: p.acceptance,
    date: p.startDate,
    /**
     * `open` 是**纯 UI 状态**（这一行眼下是展开还是收起），不是业务数据。
     * 但它必须跟着往返：否则 PUT 回来时后端不返回它，fromBackendNode 读到的
     * 就是 undefined → 整棵树全部收起（实测点行展开→立即又缩回，看起来
     * 就是「文件无法展开」）。后端按自由 JSON 存着即可，不参与任何校验。
     */
    open: p.open,
    children: p.folders.map(toBackendNode),
    deliverables: p.deliverables.map((d) => ({
      date: d.date,
      doc: d.name,
      ver: d.version,
      state: d.state,
      subpath: d.subpath,
      planned: d.planned,
    })),
  }
}

export async function getContractStages(contractId: number): Promise<PhaseNode[]> {
  const res = await contractsApi.get(`contracts/${contractId}/stages`).json<ContractStagesResponse>()
  const raw = (res?.stages ?? []) as unknown as Record<string, unknown>[]
  return normalizeTree(raw.map(fromBackendNode))
}

/**
 * 提交整棵阶段树。
 *
 * 整棵覆盖而不是逐节点 patch：律师在弹窗里可能一次改名 + 升降级 + 删子阶段，
 * 逐条提交会产生中间态（「先删父阶段、再加子阶段」的顺序一旦颠倒就丢节点）。
 * 整树提交是幂等的，也与后端 `stages` 是 JSONField 的存储形状一致。
 */
export async function putContractStages(contractId: number, stages: PhaseNode[]): Promise<PhaseNode[]> {
  const res = await contractsApi
    .put(`contracts/${contractId}/stages`, { json: { stages: stages.map(toBackendNode) } })
    .json<ContractStagesResponse>()
  const raw = (res?.stages ?? []) as unknown as Record<string, unknown>[]
  return raw.length ? normalizeTree(raw.map(fromBackendNode)) : stages
}
