/**
 * 把 AI 直改的修订**就地**落进打开中的 DS 画布（免整页重载）。
 *
 * 通道（协议见 deploy/onlyoffice/plugins/fachuan-rewrite/plugin.js）：
 * 页面 → 插件桥 `apply-revision {orig, sug}` → DS 内核开修订模式、定位
 * 原文并替换 → 画布里直接长出修订痕迹。任何一环不通（插件未握手、原文
 * 找不到、内核超时）都 resolve(false)，use-rewrite-refresh 据此降级为换
 * key 重载——失败路径与没有本 hook 时完全一致。
 *
 * 监听挂在 window 上而非借 OfficeView 的 onPluginMessage 转发：插件桥的
 * 消息本来就 postMessage 到宿主窗口，直接听省去调用方接线；FilePreview
 * 这类没接 onPluginMessage 的挂载点也因此同享就地落笔。
 */

import { useEffect, useRef } from 'react'

import type { OfficeEditorHandle, PluginBridgeMessage } from '@/components/shared/onlyoffice/OfficeView'

import { registerLiveRewriteApply } from './use-rewrite-refresh'

/**
 * 等插件回执的上限。
 *
 * **必须 >= plugin.js 的 COMMAND_TIMEOUT_MS（当前 8s）+ 1s 余量**：插件自己会
 * 在 8s 报超时并回一条 `applied{ok:false}`，前端若先超时就会把它当成
 * 「插件没反应」提前降级成换 key 重建画布（= 整页刷一下）。两边对齐后，
 * 永远是插件先给结论，前端只在桥彻底失联时才自己超时。
 */
const APPLY_TIMEOUT_MS = 10000

export function useLiveRewriteApply({ enabled, key }: {
  /** docx 才注册：插件只在 word 的 edit/review 态 autostart */
  enabled: boolean
  /** 与 use-rewrite-refresh 同口径的文件 key：`contract:${ownerId}:${subpath}` */
  key: string
}): {
  /** 挂到 OfficeView 的 onEditorReady（与既有句柄保存逻辑并联调用） */
  onEditorReady: (h: OfficeEditorHandle | null) => void
} {
  const editorRef = useRef<OfficeEditorHandle | null>(null)
  const pluginReadyRef = useRef(false)
  /** 在途一次 apply 的回执槽：插件是单槽回调，同 key 同时只该有一条 */
  const pendingRef = useRef<{ resolve: (ok: boolean) => void; timer: number } | null>(null)

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const d = e.data as (PluginBridgeMessage & { source?: string }) | null
      if (!d || d.source !== 'fachuan-plugin') return
      if (d.type === 'ready' || d.type === 'hello') pluginReadyRef.current = d.supported !== false
      if (d.type === 'applied' && pendingRef.current) {
        const { resolve, timer } = pendingRef.current
        pendingRef.current = null
        window.clearTimeout(timer)
        resolve(!!(d.result && d.result.ok))
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  useEffect(() => {
    if (!enabled) return
    return registerLiveRewriteApply(key, (original, replacement) =>
      new Promise<boolean>((resolve) => {
        const h = editorRef.current
        // 编辑器没就绪 / 桥没握手：立刻让位给重载路径，不白等超时
        if (!h || !pluginReadyRef.current) return resolve(false)
        const timer = window.setTimeout(() => {
          pendingRef.current = null
          resolve(false)
        }, APPLY_TIMEOUT_MS)
        pendingRef.current = { resolve, timer }
        h.sendToPlugin('apply-revision', undefined, { orig: original, sug: replacement })
      }),
    )
  }, [enabled, key])

  return {
    onEditorReady: (h) => {
      editorRef.current = h
      // 画布重建（换 key 重载/换文件）后插件重新握手，ready 态作废重记
      if (!h) pluginReadyRef.current = false
    },
  }
}
