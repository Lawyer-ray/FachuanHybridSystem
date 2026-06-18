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
  if (sdkLoaded) return Promise.resolve()
  if (loadingPromise) return loadingPromise

  loadingPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `${portalUrl}/static/scripts/sdk/2.1.0/api.js`
    script.async = true
    script.onload = () => {
      sdkLoaded = true
      resolve()
    }
    script.onerror = () => {
      loadingPromise = null
      reject(new Error('Failed to load DocSpace SDK'))
    }
    document.head.appendChild(script)
  })

  return loadingPromise
}

export function isDocSpaceSDKLoaded(): boolean {
  return sdkLoaded && !!window.DocSpace
}
