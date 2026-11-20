/**
 * 评审采纳记录（`/agent/reviews/{review_id}/adopt` 与 `/adoption`）的前端映射。
 *
 * 采纳是**独立于 `Review` 判定快照的一次决定**：`Review` 只读、不可变，采纳
 * 记录单独落一行、单独回读。所以类型与映射也单独成文件——不要把 `adopted`
 * 塞回冻结的 `adjudication-types.ts`（那会让"判定快照"多一个会变的字段）。
 *
 * 线上格式（snake_case）：
 *
 * - `POST /agent/reviews/{id}/adopt` body `{lane: string | null, merged: boolean, note: string}`
 *   → `{review_id, lane, merged, note, adopted_at}`；
 * - `GET /agent/reviews/{id}/adoption` → `{adoption: {...} | null}`（404 = 没有记录）。
 *
 * `lane === null && merged === false` 不是一次有效裁决——它既没选栏也没标合并，
 * 映射层直接当成"没有采纳记录"，绝不让 UI 渲染成「采纳了空栏」。
 */

/** POST/GET 的采纳记录（线上形状） */
export interface ReviewAdoptionWire {
  review_id: string
  lane: string | null
  merged: boolean
  note: string
  adopted_at: string
}

/** `GET .../adoption` 的信封（没有记录时 `adoption: null`） */
export interface ReviewAdoptionEnvelope {
  adoption: ReviewAdoptionWire | null
}

/** `POST .../adopt` 的请求体（与线上同形：字段名就是线上字段） */
export interface ReviewAdoptPayload {
  lane: string | null
  merged: boolean
  note: string
}

/** 采纳记录的视图（camelCase） */
export interface AdoptionView {
  reviewId: string
  /** 采纳的那一栏；`null` = 标为合并（不是"采纳了空栏"） */
  lane: string | null
  merged: boolean
  note: string
  /** 服务端时间**原样透传**：时区/格式由展示层决定，映射层不本地化 */
  adoptedAt: string
}

/**
 * 线上采纳记录 → 视图；无效记录（没选栏也没标合并）→ `null`。
 *
 * 空串栏同样归一到 `null`：线上契约是 `string | null`，空串只可能是脏数据，
 * 让它原样进 UI 就会渲染出「已采纳 」这种半截文案。
 */
export function toAdoptionView(wire: ReviewAdoptionWire | null | undefined): AdoptionView | null {
  if (!wire) return null
  const lane = typeof wire.lane === 'string' && wire.lane !== '' ? wire.lane : null
  const merged = wire.merged === true
  if (lane === null && !merged) return null
  return {
    reviewId: wire.review_id,
    lane,
    merged,
    note: wire.note ?? '',
    adoptedAt: wire.adopted_at,
  }
}

/**
 * 采纳回显的一句话。`labelOf` 把栏 kind 翻成栏头显示名（未知 kind 原样）。
 *
 * 「标为合并」与「采纳某一栏」是两件事：合并没有栏，文案里不能出现一个空栏名。
 */
export function adoptionSummary(adoption: AdoptionView, labelOf: (lane: string) => string = (lane) => lane): string {
  if (adoption.lane !== null) return `已采纳 ${labelOf(adoption.lane)}`
  return adoption.merged ? '已标为合并采纳' : ''
}
