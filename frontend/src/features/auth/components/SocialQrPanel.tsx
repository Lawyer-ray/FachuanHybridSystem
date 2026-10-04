/**
 * 飞书内嵌二维码登录面板。
 *
 * 安全要点（缺一不可）：
 * 1. postMessage 必须同时校验 event.origin（matchOrigin）与 event.data（matchData）。
 *    只校验 origin 不校验 data，任何人都能在同源页面 postMessage 伪造登录结果；
 *    只校验 data 不校验 origin，则任意 iframe 都能冒充分享父窗口消息。
 * 2. tmp_code 必须拼接在 goto 上跳转，由飞书 302 换真授权码；
 *    前端不得自行把 tmp_code 当授权码使用。
 * 3. state 由后端生成并存 session，前端只透传，不参与生成。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { socialAuthApi, type SocialProviderInfo, type SocialSession } from '../social-api'
import { FEISHU_QR_SDK_URL } from '../constants'

/** QRLogin 实例暴露的校验方法 */
interface QrLoginInstance {
  matchOrigin: (origin: string) => boolean
  matchData: (data: unknown) => boolean
}

type QrLoginFactory = (options: {
  id: string
  goto: string
  width?: string
  height?: string
  style?: string
}) => QrLoginInstance

declare global {
  interface Window {
    QRLogin?: QrLoginFactory
    __feishuQrSdkLoading?: Promise<void>
  }
}

function loadFeishuQrSdk(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve()
  if (window.QRLogin) return Promise.resolve()
  if (window.__feishuQrSdkLoading) return window.__feishuQrSdkLoading

  const loading = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = FEISHU_QR_SDK_URL
    script.async = true
    script.onload = () => (window.QRLogin ? resolve() : reject(new Error('飞书登录组件加载失败')))
    script.onerror = () => reject(new Error('飞书登录组件加载失败，请检查网络'))
    document.head.appendChild(script)
  })
  window.__feishuQrSdkLoading = loading
  // 失败必须清掉全局缓存：否则 rejected promise 被永久挂在 window 上，
  // 错误态的「重新加载」会拿到同一个 rejected promise，重试永远失败，只能整页刷新
  return loading.catch((e) => {
    if (window.__feishuQrSdkLoading === loading) delete window.__feishuQrSdkLoading
    throw e
  })
}

interface Props {
  provider: SocialProviderInfo
  /** 授权会话来源：登录页用默认（登录 session），绑定页传 bind-session */
  createSession?: (provider: string) => Promise<SocialSession>
  /** 二维码容器 id：同一页面可能同时存在多个面板，必须唯一 */
  containerId?: string
}

export function SocialQrPanel({ provider, createSession, containerId = 'feishu-qr-container' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const qrInstanceRef = useRef<QrLoginInstance | null>(null)
  const gotoRef = useRef<string>('')
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState('')
  // 依赖收敛为原始值：providers query 每次 refetch 生成新数组/新对象，
  // boot 若依赖 provider 对象身份，refetch 一次二维码就闪换重画（session 作废重来）
  const providerName = provider.name
  const qrWidth = provider.client_config?.width
  const qrHeight = provider.client_config?.height

  const fail = useCallback((message: string) => {
    setState('error')
    setError(message)
  }, [])

  /** 初始化二维码：拉授权 URL → 注入 SDK → 渲染。
   *  每个 await 之后都先确认组件仍挂载（containerRef 还在），卸载后到达的
   *  异步结果不再碰 DOM / state（StrictMode 双挂载、面板快速切换都安全）。 */
  const boot = useCallback(async () => {
    const container = containerRef.current
    if (!container) return
    const gone = () => containerRef.current === null

    setState('loading')
    setError('')

    let session: SocialSession
    try {
      session = await (createSession ?? socialAuthApi.createSession)(providerName)
    } catch (err) {
      if (!gone()) fail(err instanceof Error ? err.message : '登录方式暂不可用，请稍后再试或联系管理员')
      return
    }

    // state 由后端签发，goto 里已带；刷新二维码时重新申请，避免复用过期 state
    gotoRef.current = session.goto

    try {
      await loadFeishuQrSdk()
    } catch (err) {
      if (!gone()) fail(err instanceof Error ? err.message : '飞书登录组件加载失败')
      return
    }

    // 每次刷新都清空容器，防止二维码重复堆叠
    container.innerHTML = ''
    const qrLogin = window.QRLogin
    if (!qrLogin) {
      if (!gone()) fail('飞书登录组件加载失败')
      return
    }

    qrInstanceRef.current = qrLogin({
      id: container.id,
      goto: session.goto,
      width: qrWidth ?? '260',
      height: qrHeight ?? '260',
    })
    if (!gone()) setState('ready')
  }, [providerName, qrWidth, qrHeight, fail, createSession])

  useEffect(() => {
    void boot()
  }, [boot])

  /** 监听 SDK 的扫码消息，校验后拼 tmp_code 跳转 */
  useEffect(() => {
    /** 校验消息来源与内容，任一不过关即视为伪造并丢弃 */
    const isValidScanMessage = (event: MessageEvent): string | null => {
      const instance = qrInstanceRef.current
      if (!instance) return null
      try {
        if (!instance.matchOrigin(event.origin) || !instance.matchData(event.data)) return null
      } catch {
        // SDK 校验方法本身抛异常时同样视为不可信
        return null
      }
      const tmpCode = (event.data as { tmp_code?: unknown })?.tmp_code
      return typeof tmpCode === 'string' && tmpCode ? tmpCode : null
    }

    const handleMessage = (event: MessageEvent) => {
      const tmpCode = isValidScanMessage(event)
      if (!tmpCode) return

      // 交给飞书换取真授权码：整页导航，session cookie 与后端同源可正常携带
      const goto = gotoRef.current
      window.location.href = `${goto}&tmp_code=${encodeURIComponent(tmpCode)}`
    }

    window.addEventListener('message', handleMessage, false)
    return () => window.removeEventListener('message', handleMessage, false)
  }, [])

  if (state === 'error') {
    return (
      <div className="fc-qr">
        <p className="fc-hint fc-hint--error">{error || '二维码加载失败'}</p>
        <button type="button" className="fc-btn fc-btn--ghost" onClick={() => void boot()}>
          重新加载
        </button>
      </div>
    )
  }

  return (
    <div className="fc-qr">
      {/* 顶部章节带：与表单栏节奏对齐，给二维码一个「开始扫描」的起点。
          状态文案跟着 state 走，loading 时不再谎报 READY。 */}
      <div className="fc-qr__band fc-qr__band--top">
        <span className="fc-qr__band-label">§ 02.01 · SCAN</span>
        <span className="fc-qr__band-status">
          <span aria-hidden className="fc-qr__band-dot" />
          {state === 'ready' ? 'READY' : 'CONNECTING'}
        </span>
      </div>

      {/* 框选层：黄铜 L 形角标落在浅色底板外沿，编辑风的「扫描区」 */}
      <div className="fc-qr__frame">
        <span aria-hidden className="fc-qr__corner fc-qr__corner--tl" />
        <span aria-hidden className="fc-qr__corner fc-qr__corner--tr" />
        <span aria-hidden className="fc-qr__corner fc-qr__corner--bl" />
        <span aria-hidden className="fc-qr__corner fc-qr__corner--br" />

        <div className="fc-qr__plate">
          {/* 二维码挂载点：id 供 QRLogin 使用。
              注意：容器内部完全交给飞书 SDK 的 innerHTML 操作，React 不得在其内部渲染
              任何子节点——否则 SDK 清空容器后，React 再尝试卸载自己渲染的旧节点时会
              因为该节点已被直接移除而抛出 removeChild NotFoundError，导致整棵树崩溃、
              页面白屏（这里没有 Error Boundary 兜底）。加载态改为绝对定位的同级元素。 */}
          <div className="relative flex min-h-[168px] min-w-[168px] items-center justify-center">
            <div
              id={containerId}
              ref={containerRef}
              className="flex min-h-[168px] min-w-[168px] items-center justify-center"
              aria-label={`${provider.display_name}扫码登录`}
            />
            {state === 'loading' && (
              <Loader2 className="absolute size-5 animate-spin text-[#8b8578]" />
            )}
          </div>
        </div>
      </div>

      {/* 底部章节带：标识「谁在登录」 */}
      <div className="fc-qr__band fc-qr__band--bottom">
        <span className="fc-qr__band-label">{provider.display_name} · 二维码</span>
        <span className="fc-qr__band-meta">SCAN TO LOGIN</span>
      </div>

      {/* 双行指引：第一行亮，名字黄铜；副行小一号且暗 */}
      {state === 'ready' && (
        <div className="fc-qr__guide">
          <p>
            打开 <strong>{provider.display_name}</strong> APP 扫一扫
          </p>
          <p className="fc-qr__guide-sub">在手机上确认后即完成登录</p>
        </div>
      )}
    </div>
  )
}
