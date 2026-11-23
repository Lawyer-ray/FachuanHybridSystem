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

/**
 * 页面上「单个文件 ≤ xxMB」的提示数字（仅文案，不参与任何前端校验）。
 *
 * 服务端口径见 `backend/apps/message_hub/services/upload_policy.py`：公开上传链接
 * 与律师手动上传共用 `validate_manual_upload_file`，上限按「压缩包 / 非压缩包」
 * 各取 `MANUAL_UPLOAD_ARCHIVE_MAX_SIZE_BYTES` / `MANUAL_UPLOAD_MAX_SIZE_BYTES`。
 *
 * 注意：后端两个上限当前都放宽到了 1GB（单文件与压缩包同额），与本处 50/200
 * 已不一致——这是既有文案偏差，本次只做字面量收敛、不改对客口径，改数字需单独确认。
 */
export const MAX_SINGLE_FILE_MB = 50
/** 压缩包上限（同上：仅文案，后端同口径见 upload_policy.py） */
export const MAX_ARCHIVE_MB = 200
