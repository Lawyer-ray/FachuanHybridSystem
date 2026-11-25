import { useEffect } from 'react'

import { createApiClient } from '@/lib/api'

import type { FolderOwnerKind } from '../../api'

/**
 * 告诉后端「这份文件的画布现在开着」。
 *
 * ## 为什么需要它
 *
 * AI 写完盘之后，前端要把这条修订**重放进当前画布**（免整页重建）；没人在看
 * 这份文件时重放纯属浪费，而且会让 `OfficeView` 白跑一轮插件桥。
 * 后端拿不到「浏览器里有没有画布」这个事实——`EditorSession` 是持久的，律师关掉
 * 标签页之后那行还在。所以只能由前端主动登记。
 *
 * ## 为什么是心跳而不是只发一次
 *
 * 浏览器崩掉、标签页被强杀时，`beforeunload` 不一定执行。后端按 TTL（90 秒）
 * 过期，前端每 30 秒续期一次：丢一次心跳不会误判「没开」，真关了也会在 90 秒内
 * 自动收敛回「没开」。
 *
 * ## 失败必须静默
 *
 * 这是个**优化信号**，不是正确性前提（写盘永远做，见 `DocWriteService`）。
 * 登记失败只意味着「这次不做重放」，绝不能弹错打扰律师。
 */

const HEARTBEAT_MS = 30_000

let _api: ReturnType<typeof createApiClient> | null = null
function presenceApi() {
  // 延迟创建：App 级测试会整体加载本模块，mock 的 @/lib/api 未必带 createApiClient
  _api ??= createApiClient({ prefix: '/api/v1/doc-workspace' })
  return _api
}

function push(kind: FolderOwnerKind, ownerId: number, subpath: string, open: boolean): void {
  void presenceApi()
    .post('canvas-presence', { json: { kind, owner_id: ownerId, subpath, open } })
    .catch(() => {
      /* 优化信号，失败即当作「没开画布」 */
    })
}

export function useCanvasPresence(
  kind: FolderOwnerKind,
  ownerId: number | undefined,
  subpath: string | undefined,
  enabled: boolean,
): void {
  useEffect(() => {
    if (!enabled || ownerId == null || !subpath) return
    push(kind, ownerId, subpath, true)
    const timer = window.setInterval(() => push(kind, ownerId, subpath, true), HEARTBEAT_MS)
    return () => {
      window.clearInterval(timer)
      push(kind, ownerId, subpath, false)
    }
  }, [kind, ownerId, subpath, enabled])
}
