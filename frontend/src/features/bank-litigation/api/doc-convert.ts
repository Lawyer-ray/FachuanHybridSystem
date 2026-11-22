import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

import { DOC_CONVERT_TIMEOUT_MS } from './timeouts'

// ───────────────────────── 要素式转换 ─────────────────────────

export const docConvertApi = createApiClient({ prefix: '/api/v1/doc-convert' })

/** 文书类型（按类别分组） */
export type MbidList = components['schemas']['MbidListResponse']

export async function listMbidTypes(): Promise<MbidList> {
  return docConvertApi.get('mbid-list').json<MbidList>()
}

/**
 * 传统文书 → 要素式文书。
 *
 * ⚠️ 两点与普通接口不同：
 * 1. `multipart/form-data`：必须传 FormData，不能传 json；
 * 2. **响应是 docx 二进制流**，不是 JSON。所以要 `.blob()`，且文件名在
 *    Content-Disposition 里（`filename*=UTF-8''...`），需要自己解。
 *
 * 后端要求 `ZNSZJ_ENABLED=True`，未开启时返回 403。
 */
export async function convertToElemental(file: File, mbid: string): Promise<Blob> {
  const form = new FormData()
  form.append('file', file)
  form.append('mbid', mbid)
  const res = await docConvertApi.post('convert', {
    // ⚠️ ky 的 FormData 走 `body:`，不是 `json:` —— 写成 json 会让 ky
    // 去序列化 FormData（结果是空 body 或直接抛错），请求发不出去，
    // 界面永远停在「转换中…」。参考 material-prep 的 uploadPack 写法。
    body: form,
    // 转换要过一遍服务端的文档解析，比普通请求慢得多；用上传档的超时。
    timeout: DOC_CONVERT_TIMEOUT_MS,
  })
  return res.blob()
}

/** 历史转换记录（最新在前，供历史弹窗浏览与重新下载） */
export type ConvertRecordList = components['schemas']['DocConvertRecordListOut']

export async function listConvertRecords(): Promise<ConvertRecordList> {
  return docConvertApi.get('records').json<ConvertRecordList>()
}
