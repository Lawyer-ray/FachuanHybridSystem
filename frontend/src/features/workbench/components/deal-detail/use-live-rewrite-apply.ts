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

import { ackCanvasSynced } from '@/components/shared/onlyoffice/api'
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

export function useLiveRewriteApply({ enabled, key, fileUrl }: {
  /** docx 才注册：插件只在 word 的 edit/review 态 autostart */
  enabled: boolean
  /** 与 use-rewrite-refresh 同口径的文件 key：`contract:${ownerId}:${subpath}` */
  key: string
  /**
   * 站内文件路径（与签配置同一个串）。**就地落笔成功后要拿它去登记画布已同步**，
   * 漏掉这一步的后果见下面 `ackCanvasSynced` 的注释。
   */
  fileUrl: string
}): {
  /** 挂到 OfficeView 的 onEditorReady（与既有句柄保存逻辑并联调用） */
  onEditorReady: (h: OfficeEditorHandle | null) => void
} {
  const editorRef = useRef<OfficeEditorHandle | null>(null)
  const pluginReadyRef = useRef(false)
  /**
   * ack 需要 fileUrl，而消息监听 effect 只挂一次（不能把 fileUrl 放进它的依赖，
   * 否则每换一次文件就重挂监听，还可能把在途回执丢掉）：用 ref 取最新值。
   *
   * ref 只能在 effect 里写（渲染期写 ref 会被 react-hooks/refs 拦）。这条
   * effect 必须排在下面的监听 effect **之前**，否则首次挂载时 ref 还是旧值。
   */
  const fileUrlRef = useRef(fileUrl)
  useEffect(() => {
    fileUrlRef.current = fileUrl
  }, [fileUrl])
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
        if (!(d.result && d.result.ok)) {
          resolve(false)
          return
        }
        /**
         * 画布上已经长出修订痕迹，但后端只知道「磁盘被外部写过」（external_write_seq
         * 抬了一代，canvas_seq 还是旧的）。不把「画布已同步」登记回去，律师接着
         * 在这份画布上编辑并保存时，后端会把这次保存当成**旧画布覆盖**而丢掉，
         * 并且为了不让 DS 无限重试仍应答 `error:0` —— 律师看到「已保存」，
         * 内容却没落盘。
         *
         * ack 失败就当作「就地落笔失败」返回 false：宁可降级成换 key 重载
         * （慢但正确），也不能留一个「以为同步了、其实没同步」的画布。
         */
        const path = fileUrlRef.current
        if (!path) {
          resolve(false)
          return
        }
        void ackCanvasSynced(path)
          .then((r) => resolve(!!r.ok))
          .catch(() => resolve(false))
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
