/**
 * 客户上传公开端点客户端（/api/v1/public/material-link*）。
 * token 经 X-Upload-Token 头传递（不进 URL/访问日志，对齐后端设计）。
 * 未登录页面：createApiClient 的 Bearer 注入在此场景天然不生效，已登录
 * 律师自测链接时多带的 Authorization 头会被公开端点忽略，无副作用。
 */

import { API_BASE_URL, createApiClient } from '@/lib/api'
import type { PublicFileItem, PublicLinkInfo, PublicUploadResult } from './types'

const TOKEN_HEADER = 'X-Upload-Token'

const publicApi = createApiClient({ prefix: '/api/v1/public' })

const tokenHeaders = (token: string): Record<string, string> => ({ [TOKEN_HEADER]: token })

export async function getLinkInfo(token: string): Promise<PublicLinkInfo> {
  return publicApi.get('material-link', { headers: tokenHeaders(token) }).json<PublicLinkInfo>()
}

export async function listUploadedFiles(token: string): Promise<PublicFileItem[]> {
  return publicApi.get('material-link/files', { headers: tokenHeaders(token) }).json<PublicFileItem[]>()
}

/** 解析后端错误信封（{success:false, message}），给 XHR 失败一个可读文案 */
function extractMessage(raw: string, fallback: string): string {
  try {
    const body = JSON.parse(raw) as { message?: unknown; detail?: unknown }
    const msg = body.message ?? body.detail
    return typeof msg === 'string' && msg ? msg : fallback
  } catch {
    return fallback
  }
}

/**
 * 带上传进度的提交：ky（fetch）拿不到 upload progress，改用原生 XHR。
 * 失败 reject Error(message)，页面直接展示 message（服务端已给出可读中文）。
 */
export function uploadFiles(
  token: string,
  files: File[],
  remark: string,
  onProgress?: (percent: number) => void,
): Promise<PublicUploadResult> {
  return new Promise((resolve, reject) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f, f.name)
    if (remark.trim()) fd.append('remark', remark.trim())

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/public/material-link/files`)
    xhr.setRequestHeader(TOKEN_HEADER, token)
    xhr.timeout = 300_000
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as PublicUploadResult)
        } catch {
          reject(new Error('服务返回异常，请重试'))
        }
        return
      }
      reject(new Error(extractMessage(xhr.responseText, `上传失败（${xhr.status}），请重试`)))
    }
    xhr.onerror = () => reject(new Error('网络错误，请检查网络后重试'))
    xhr.ontimeout = () => reject(new Error('上传超时，请重试'))
    xhr.send(fd)
  })
}
