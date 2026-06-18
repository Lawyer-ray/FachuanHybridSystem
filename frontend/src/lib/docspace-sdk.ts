/**
 * DocSpace JS SDK 动态加载器。
 * 仅在首次调用时加载 (~200KB)，后续复用已加载的实例。
 */

let sdkLoaded = false
let loadingPromise: Promise<void> | null = null

declare global {
  interface Window {
    DocSpace?: {
      SDK: {
        initEditor: (config: Record<string, unknown>) => unknown
        init: (config: Record<string, unknown>) => unknown
        frames: Record<string, unknown>
      }
    }
  }
}

export function loadDocSpaceSDK(portalUrl: string): Promise<void> {
  if (sdkLoaded && window.DocSpace) return Promise.resolve()
  if (loadingPromise) return loadingPromise

  const sdkUrl = `${portalUrl}/static/scripts/sdk/2.1.0/api.js`
  console.log('[DocSpace] 开始加载 SDK:', sdkUrl)

  loadingPromise = new Promise<void>((resolve, reject) => {
    const existed = document.querySelector(`script[src="${sdkUrl}"]`)
    if (existed) {
      console.log('[DocSpace] 脚本已存在，等待 SDK 就绪…')
      _waitForSDK(resolve, reject)
      return
    }

    const script = document.createElement('script')
    script.src = sdkUrl
    script.onload = () => {
      console.log('[DocSpace] 脚本 onload 触发, window.DocSpace =', !!window.DocSpace)
      _waitForSDK(resolve, reject)
    }
    script.onerror = (e) => {
      console.error('[DocSpace] 脚本加载失败:', e)
      loadingPromise = null
      reject(new Error('DocSpace SDK 脚本加载失败'))
    }
    document.head.appendChild(script)
  })

  return loadingPromise
}

function _waitForSDK(resolve: () => void, reject: (e: Error) => void) {
  let tries = 0
  const timer = setInterval(() => {
    if (window.DocSpace?.SDK) {
      clearInterval(timer)
      sdkLoaded = true
      console.log('[DocSpace] SDK 就绪')
      resolve()
    } else if (++tries > 50) {
      clearInterval(timer)
      loadingPromise = null
      console.error('[DocSpace] SDK 超时, window.DocSpace =', window.DocSpace)
      reject(new Error('DocSpace SDK 加载超时'))
    }
  }, 100)
}

export function isDocSpaceSDKLoaded(): boolean {
  return sdkLoaded && !!window.DocSpace
}
