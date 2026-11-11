import { UPLOAD_TIMEOUT_MS } from '@/lib/api'
import { inboxApi } from './inbox-packs'
import type { OcrResult } from '../types'

/** 框选取字：把页面图片交给 RapidOCR，返回归一化文字块 */
export async function ocrImage(image: Blob): Promise<OcrResult> {
  const fd = new FormData()
  fd.append('file', image, 'page.png')
  return inboxApi
    .post('ocr', { body: fd, timeout: UPLOAD_TIMEOUT_MS })
    .json<OcrResult>()
}
