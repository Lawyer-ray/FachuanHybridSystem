/**
 * 客户上传单页的本域运行时常量。
 *
 * 与 `types.ts` 分文件：`types.ts` 只放类型，才能被 `import type` 整体擦除
 * （否则「只引类型」的模块会意外进入运行期依赖图）。
 */

import type { LinkState } from './types'

/** 链接已关闭的三种原因 → 页面提示文案（state 为 open 时不会用到） */
export const CLOSED_STATE_TEXT: Record<Exclude<LinkState, 'open'>, string> = {
  expired: '链接已过期',
  revoked: '链接已作废',
  full: '链接已收满',
}

/** 允许上传的类型（与服务端白名单同口径；仅前端提示，最终校验在服务端） */
export const ACCEPT_ATTR = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.jpg,.jpeg,.png,.gif,.webp,.bmp,.tiff,.heic,.zip,.rar,.7z'
