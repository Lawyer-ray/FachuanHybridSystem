/**
 * AI 直改覆写文件后的「编辑器刷新」信号（消费 copilot 的 file-rewritten 事件）。
 *
 * ## 为什么 nonce 放模块级 Map 而不是组件 state
 *
 * AI 落盘发生在流式对话期间，画布组件可能（a）还没挂载、（b）因重挂/换文件
 * 重建。组件 state 两条都接不住；模块级 Map 与 window 事件同生命周期，
 * 计数只增不减，画布挂载时读到的就是「这份文件被覆写过几次」。
 *
 * ## 刷新机制（两级）
 *
 * 1. **就地落修订**（首选）：file-rewritten 事件带 original/replacement 且
 *    该文件有画布注册了就地通道（useLiveRewriteApply）时，走插件桥把修订
 *    直接落进**打开中的** DS 画布——不重载、不丢滚动位置，律师看着修订
 *    痕迹长出来。落笔失败（插件未握手/原文找不到/内核超时）自动降级 2。
 * 2. **换 key 重载**（兜底）：nonce 作为 OfficeView 的 `version` 传入：
 *    变化 → 重签编辑器配置 → 后端按（已 bump 的 saved_version）算出**新
 *    document key** → DS 拉盘上已覆写的内容，修订痕迹随之可见。key 不换
 *    的话 DS 永远回旧缓存，这正是「AI 说已改好、编辑器却没有任何改动
 *    痕迹」的根因。
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

/** 就地落修订通道：key 同 nonces；由挂载中的画布（useLiveRewriteApply）注册 */
type LiveApplier = (original: string, replacement: string) => Promise<boolean>
const liveAppliers = new Map<string, LiveApplier>()

/** 挂载中的画布注册就地落笔通道；返回注销函数（同 key 重复注册以最新为准） */
export function registerLiveRewriteApply(key: string, applier: LiveApplier): () => void {
  liveAppliers.set(key, applier)
  return () => {
    if (liveAppliers.get(key) === applier) liveAppliers.delete(key)
  }
}

/**
 * 事件串行处理：一轮里连续多次直改时，前一条的插件回调没回来就发下一条，
 * 会把 plugin.js 的单槽 onCommandCallback 覆盖掉（表现为前一条超时、整页
 * 重载）。排队等前一条落定（就地成功 / 降级重载）再发下一条。
 */
let queue: Promise<void> = Promise.resolve()

function enqueueRewrite(detail: FileRewrittenDetail): void {
  queue = queue.then(() => handleRewrite(detail)).catch(() => {
    /* 处理链自身异常不阻塞后续事件 */
  })
}

async function handleRewrite(d: FileRewrittenDetail): Promise<void> {
  const key = `contract:${d.contractId}:${d.subpath}`
  const { original, replacement } = d
  const live = original && replacement ? liveAppliers.get(key) : undefined
  if (live && original && replacement) {
    const applied = await live(original, replacement).catch(() => false)
    if (applied) {
      toast.success(`AI 修订已写入《${d.name}》`, { description: '已在打开的文档中生成，可直接审阅' })
      return
    }
  }
  nonces.set(key, (nonces.get(key) ?? 0) + 1)
  epoch += 1
  for (const l of listeners) l()
  // toast 放模块监听器（唯一实例）：右栏卡与整页预览可能同时挂载，
  // 组件级监听会弹两次
  toast.success(`AI 修订已写入《${d.name}》`, { description: '正在刷新打开的文档，稍候即可看到修订痕迹' })
}

if (typeof window !== 'undefined') {
  window.addEventListener(FILE_REWRITTEN_EVENT, (e) => {
    const d = (e as CustomEvent<FileRewrittenDetail>).detail
    if (!d || !Number.isFinite(d.contractId) || !d.subpath) return
    // 落盘端点只认合同；kind 固定 'contract'，与 FilePreviewCard 传入的
    // key 口径一致（案件文件的 nonce 永远是 0，本来也没有直改通道）
    enqueueRewrite(d)
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
