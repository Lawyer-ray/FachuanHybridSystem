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

  loadingPromise = new Promise<void>((resolve, reject) => {
    const existed = document.querySelector(`script[src*="/static/scripts/sdk/"]`)
    if (existed) {
      // 脚本已存在，等 DocSpace 对象就绪
      _waitForSDK(resolve, reject)
      return
    }

    const script = document.createElement('script')
    script.src = `${portalUrl}/static/scripts/sdk/2.1.0/api.js`
    script.onload = () => _waitForSDK(resolve, reject)
    script.onerror = () => {
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
      resolve()
    } else if (++tries > 50) { // 5 秒超时
      clearInterval(timer)
      loadingPromise = null
      reject(new Error('DocSpace SDK 加载超时'))
    }
  }, 100)
}

export function isDocSpaceSDKLoaded(): boolean {
  return sdkLoaded && !!window.DocSpace
}
