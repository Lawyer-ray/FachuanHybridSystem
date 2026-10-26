/**
 * AI 直改覆写文件后的「编辑器刷新」信号（消费 copilot 的 file-rewritten 事件）。
 *
 * ## 为什么 nonce 放模块级 Map 而不是组件 state
 *
 * AI 落盘发生在流式对话期间，画布组件可能（a）还没挂载、（b）因重挂/换文件
 * 重建。组件 state 两条都接不住；模块级 Map 与 window 事件同生命周期，
 * 计数只增不减，画布挂载时读到的就是「这份文件被覆写过几次」。
 *
 * ## 刷新机制
 *
 * nonce 作为 OfficeView 的 `version` 传入：变化 → 重签编辑器配置 → 后端按
 * （已 bump 的 saved_version）算出**新 document key** → DS 拉盘上已覆写的
 * 内容，修订痕迹随之可见。key 不换的话 DS 永远回旧缓存，这正是
 * 「AI 说已改好、编辑器却没有任何改动痕迹」的根因。
 */

import { useSyncExternalStore } from 'react'
import { toast } from 'sonner'

import { FILE_REWRITTEN_EVENT, type FileRewrittenDetail } from '@/features/copilot/launch'

import type { FolderOwnerKind } from '../../api'

/** 每个文件的刷新计数：key = `${kind}:${ownerId}:${subpath}` */
const nonces = new Map<string, number>()
/** 全局事件纪元：任何一次覆写 +1，驱动所有订阅组件重读自己的 nonce */
let epoch = 0
const listeners = new Set<() => void>()

if (typeof window !== 'undefined') {
  window.addEventListener(FILE_REWRITTEN_EVENT, (e) => {
    const d = (e as CustomEvent<FileRewrittenDetail>).detail
    if (!d || !Number.isFinite(d.contractId) || !d.subpath) return
    // 落盘端点只认合同；kind 固定 'contract'，与 FilePreviewCard 传入的
    // key 口径一致（案件文件的 nonce 永远是 0，本来也没有直改通道）
    const key = `contract:${d.contractId}:${d.subpath}`
    nonces.set(key, (nonces.get(key) ?? 0) + 1)
    epoch += 1
    for (const l of listeners) l()
    // toast 放模块监听器（唯一实例）：右栏卡与整页预览可能同时挂载，
    // 组件级监听会弹两次
    toast.success(`AI 修订已写入《${d.name}》`, { description: '正在刷新打开的文档，稍候即可看到修订痕迹' })
  })
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

const getEpoch = () => epoch

/**
 * 该文件被 AI 覆写过的刷新计数（0 = 从未被覆写）。
 * 直接作为 `version` 传给 OfficeView；文件未被覆写时保持空串，
 * 不改变存量文档的 key 口径。
 */
export function useFileRewriteNonce(
  kind: FolderOwnerKind,
  ownerId: number | undefined,
  subpath: string | undefined,
): number {
  useSyncExternalStore(subscribe, getEpoch)
  if (ownerId == null || !subpath) return 0
  return nonces.get(`${kind}:${ownerId}:${subpath}`) ?? 0
}
