import { createApiClient } from '@/lib/api'

/**
 * OnlyOffice 编辑器接入（Document Server）。
 *
 * 配置必须由后端签发（JWT 签名），前端只拿到「已签名的 config」——
 * DS 的 JWT_SECRET 绝不能出现在浏览器里。
 */
/** 延迟创建：避免被 App 级测试整体加载时，mock 的 @/lib/api 缺 createApiClient */
let _api: ReturnType<typeof createApiClient> | null = null
function onlyofficeApi() {
  _api ??= createApiClient({ prefix: '/api/v1/onlyoffice' })
  return _api
}

/** 编辑器模式：view 只看 / review 锁定修订 / edit 完全编辑 */
export type EditorMode = 'view' | 'review' | 'edit'

export interface EditorConfigPayload {
  enabled: boolean
  docserver_url: string
  config: Record<string, unknown> | null
  reason: string
}

/**
 * 取某文件的编辑器配置。
 *
 * `fileUrl` 传站内下载路径（如 `/api/v1/inbox/messages/1/attachments/0/download`）。
 * DS 容器带不了 Authorization 头，后端会把它换成 HMAC 签名的代理地址
 * （`/api/v1/onlyoffice/file?src=&sig=`）写进 config：签名可重复使用，
 * DS 重试 / 重连回源取文件不会被拒（旧的一次性下载票据方案已废弃）。
 * `version` 传内容版本标识（如附件 updated_at）——变了就换 DS 缓存 key。
 */
export async function getEditorConfig(
  fileUrl: string,
  fileName: string,
  mode: EditorMode = 'review',
  version = '',
): Promise<EditorConfigPayload> {
  const qs = new URLSearchParams({ file_url: fileUrl, file_name: fileName, mode, version })
  return onlyofficeApi().get(`editor-config?${qs.toString()}`).json<EditorConfigPayload>()
}

/**
 * 这份画布还能不能安全保存。
 *
 * `stale=true` = 磁盘比画布新（多半是 AI 直改过而画布没落到）。此时在画布上
 * 点保存会被后端**主动丢弃**，但为了不让 DS 无限重试，应答仍是 `error:0`——
 * 所以「保存成功」的提示可能是假的，必须靠这个接口把它说出来。
 */
export interface CanvasStatePayload {
  stale: boolean
  reason: string
  /** 最近一次「保存被丢弃」的时间（ISO）；null = 从未丢过 */
  dropped_at: string | null
}

export async function getCanvasState(fileUrl: string): Promise<CanvasStatePayload> {
  const qs = new URLSearchParams({ file_url: fileUrl })
  return onlyofficeApi().get(`canvas-state?${qs.toString()}`).json<CanvasStatePayload>()
}

/**
 * 登记「这份画布已与磁盘一致」。
 *
 * **只能在插件把 AI 修订就地落进画布且回执 ok 之后调用**。不调它，后端会一直
 * 认为画布落后于磁盘（`canvas_seq < external_write_seq`），于是律师在这份画布上
 * 之后每一次保存都被当成旧画布静默丢弃——这正是「AI 改完再改就白改」的根因。
 * 落笔失败时调它更危险：等于亲手拆掉「旧画布不得覆盖 AI 修订」的守门人。
 */
export async function ackCanvasSynced(fileUrl: string): Promise<{ ok: boolean; reason?: string }> {
  return onlyofficeApi()
    .post('canvas-ack', { json: { file_url: fileUrl } })
    .json<{ ok: boolean; reason?: string }>()
}
