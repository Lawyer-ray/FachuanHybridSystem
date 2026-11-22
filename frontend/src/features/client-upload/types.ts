/**
 * 客户上传单页（公开路由 /u/:token）的数据模型。
 * 后端端点形状取自 openapi-typescript 生成物（src/types/api-schema.d.ts）。
 */

import type { components } from '@/types/api-schema'

/** GET /public/material-link 响应（生成物 PublicLinkInfoOut；state 收窄为本域状态机） */
export type PublicLinkInfo = Omit<components['schemas']['PublicLinkInfoOut'], 'state'> & {
  state: LinkState
}

/** 已传/本批文件条目（生成物 PublicUploadFileOut） */
export type PublicFileItem = components['schemas']['PublicUploadFileOut']

/** POST /public/material-link/files 响应（生成物 PublicUploadOut） */
export type PublicUploadResult = components['schemas']['PublicUploadOut']

/** 链接状态机：open 之外的取值都是「已关闭」的不同原因（页面据此提示） */
export type LinkState = 'open' | 'expired' | 'revoked' | 'full'
