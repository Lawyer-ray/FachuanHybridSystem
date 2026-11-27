/**
 * 后端生成物的前端投影（`src/types/api-schema.d.ts` 的 `components['schemas'][...]`）。
 *
 * 从 `types.ts` 拆出：这些形状**不是本域定义的**，它们跟着后端 OpenAPI 走；
 * 这里只做「取子集 / 收窄枚举 / 补 schema 未覆盖字段」三种覆写。后端改字段时
 * 只需要看这一个文件，不用在整份材料模型里翻。
 *
 * 与 `types.ts` 之间有一处 `import type { DraftState, PackStatus }`（收窄 inbox 状态与
 * draft_state）。**必须保持 `import type`**：写成值导入就成运行时环。
 */

import type { components } from '@/types/api-schema'
import type { DraftState, PackStatus } from './types'

/** OCR 识别出的文字块（坐标为归一化 0-1 相对值；生成物 OcrBlockOut） */
export type OcrBlock = components['schemas']['OcrBlockOut']

/** OCR 整页结果（生成物 OcrResultOut） */
export type OcrResult = components['schemas']['OcrResultOut']

/** OCR 框选取字：页面上拖出的一个待确认框（坐标归一化 0-1） */
export interface OcrPending {
  mi: number
  p: number
  rect: { x: number; y: number; w: number; h: number }
  text: string
  loading: boolean
}

/** 案件搜索行（来自 /cases/search，生成物 CaseOut）。
 *  消费子集投影；id 覆写为必有（生成物按 ModelSchema 口径可选可空）。 */
export type CaseRow = Pick<
  components['schemas']['CaseOut'],
  'name' | 'filing_number' | 'case_numbers'
> & { id: number }

/** 后端 /clients 检索命中的当事人（客户库），用于委托人/对方当事人填入。
 *  基于生成物 PartyListOut；client_type 为 schema 未声明的额外字段，按可选保留 */
export type ClientHit = components['schemas']['PartyListOut'] & {
  client_type?: string | null
}

/** 收件箱附件元信息（生成物 AttachmentMeta）。
 *  PDF 页数（page_count）由后端上传时/详情读取时回填算好；缺失时前端下载 PDF 自行数页数兜底 */
// expanded_from：压缩包展开产物的来源压缩包名（后端 get_public_attachments_meta
// 透出，openapi 生成物未覆盖该字段，这里本地扩展）
export type AttachmentMeta = components['schemas']['AttachmentMeta'] & {
  expanded_from?: string | null
}

/** 收件箱消息列表项（生成物 InboxMessageOut；status 收窄为材料包三态，
 *  后端实际取值即来自本域写入 draft_state 的枚举） */
export type InboxMessage = Omit<components['schemas']['InboxMessageOut'], 'status'> & {
  status: PackStatus
}

/** 收件箱消息详情（生成物 InboxMessageDetailOut，仅覆写两处）：
 *  · status 同 InboxMessage 收窄；
 *  · draft_state 是前端自有草稿语义。从未进过阅读器的包后端返回 {}
 *   （空对象，不满足 DraftState 形状），消费方必须按「可能没有有效草稿」处理
 *   （store.open / setPackStatusRemote 均如此）。 */
export type InboxMessageDetail = Omit<
  components['schemas']['InboxMessageDetailOut'],
  'status' | 'draft_state'
> & {
  status: PackStatus
  draft_state: DraftState | Record<string, never>
}
