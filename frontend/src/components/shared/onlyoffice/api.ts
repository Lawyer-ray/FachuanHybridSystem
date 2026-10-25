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
