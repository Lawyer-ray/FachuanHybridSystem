/**
 * 归案溯源字段的口径（P0-1：让起草 RAG 消费预处理 Markdown）。
 *
 * 从 api/cases.ts 拆出：归案编排（建案/切页/上传/绑定）与「溯源字段该不该传」
 * 是两个关注点，后者是纯函数、要能单独单测；cases.ts 加上它已越过 350 行软红线。
 */

/**
 * 后端 `CaseMaterialBindItemIn` 的 `source_message_id` / `source_segment_ref` 都是可选，
 * 且**只在 `source_message_id` 非 null 时**刷新溯源（见 cases 的 binding workflow：
 * 同一附件重复绑定而调用方未带溯源时，保留既有溯源，避免把 md 链接静默清掉）。
 * 所以拿不到有效值时**整个键都不传**，而不是塞 undefined/null 脏值进去。
 *
 * `source_file_hash` 由后端自算，前端不传（传了等于伪造溯源）。
 * 段 id 缺失时仍传 message_id：包级哈希匹配可独立生效，不该因为缺段 id 就整条溯源都不给。
 */
export function bindProvenance(
  messageId: number,
  segmentRef: string | undefined,
): { source_message_id?: number; source_segment_ref?: string } {
  if (!Number.isInteger(messageId) || messageId <= 0) return {}
  const ref = (segmentRef ?? '').trim()
  return ref ? { source_message_id: messageId, source_segment_ref: ref } : { source_message_id: messageId }
}
