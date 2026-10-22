// @vitest-environment jsdom
/**
 * SocialQrPanel 测试（jsdom）。
 *
 * 本文件重点锁定安全要点（模块头注释列的三条缺一不可）：
 * 1. postMessage 必须同时通过 matchOrigin 与 matchData，任一不过即丢弃
 * 2. SDK 校验方法本身抛异常时同样视为不可信
 * 3. tmp_code 必须 encodeURIComponent 后拼到 goto 上跳转，不当授权码使用
 *
 * 另覆盖：session 申请失败 / SDK 加载失败的错误态与「重新加载」入口、
 * 加载失败后清空全局 promise 缓存（否则重试永远失败）。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const createSessionMock = vi.hoisted(() => vi.fn())

vi.mock('../social-api', () => ({
  socialAuthApi: { createSession: (...a: unknown[]) => createSessionMock(...a) },
}))

import { SocialQrPanel } from './SocialQrPanel'

/** 构造一个可用的飞书 SDK 桩，记录 matchOrigin/matchData 的调用 */
function installSdk(opts: { matchOrigin?: boolean; matchData?: boolean; throwOn?: 'origin' | 'data' } = {}) {
  const calls: string[] = []
  const factory = vi.fn(() => ({
    matchOrigin: (origin: string) => {
      calls.push('matchOrigin:' + origin)
      if (opts.throwOn === 'origin') throw new Error('sdk boom')
      return opts.matchOrigin ?? true
    },
    matchData: (data: unknown) => {
      calls.push('matchData:' + JSON.stringify(data))
      if (opts.throwOn === 'data') throw new Error('sdk boom')
      return opts.matchData ?? true
    },
  }))
  ;(window as unknown as { QRLogin?: unknown }).QRLogin = factory
  return { factory, calls }
}

function provider(name = 'feishu') {
  return { name, display_name: '飞书', client_config: {} } as never
}

/** 派发一条扫码消息 */
function postScan(data: unknown, origin = 'https://qr.example.com') {
  const e = new MessageEvent('message', { data, origin })
  window.dispatchEvent(e)
}

beforeEach(() => {
  vi.clearAllMocks()
  delete (window as unknown as { QRLogin?: unknown }).QRLogin
  delete (window as unknown as { __feishuQrSdkLoading?: unknown }).__feishuQrSdkLoading
  createSessionMock.mockResolvedValue({ goto: 'https://open.feishu.cn/authorize?state=abc' })

  // window.location.href 在 jsdom 下只读，用 defineProperty 替换成可写对象
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { href: '', origin: 'http://localhost' },
  })
})

afterEach(() => {
  delete (window as unknown as { QRLogin?: unknown }).QRLogin
})

describe('SocialQrPanel：加载与错误态', () => {
  it('session 申请失败时展示错误与重新加载入口', async () => {
    createSessionMock.mockRejectedValue(new Error('后端不可用'))
    const { container } = render(<SocialQrPanel provider={provider()} />)

    await waitFor(() => expect(screen.getByText(/后端不可用/)).toBeTruthy())
    expect(screen.getByRole('button', { name: /重新加载/ })).toBeTruthy()
    container.remove()
  })

  it('SDK 就绪后进入 ready（二维码容器存在）', async () => {
    installSdk()
    const { container } = render(<SocialQrPanel provider={provider()} />)

    await waitFor(() => expect(createSessionMock).toHaveBeenCalled())
    // SDK 已挂在 window 上，boot 会同步走到渲染
    await waitFor(() => expect(document.getElementById('feishu-qr-container')).toBeTruthy())
    container.remove()
  })

  it('点重新加载会重新申请 session', async () => {
    createSessionMock.mockRejectedValueOnce(new Error('失败')).mockResolvedValue({ goto: 'https://x' })
    installSdk()
    const { container } = render(<SocialQrPanel provider={provider()} />)

    await waitFor(() => expect(screen.getByRole('button', { name: /重新加载/ })).toBeTruthy())
    const before = createSessionMock.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: /重新加载/ }))
    await waitFor(() => expect(createSessionMock.mock.calls.length).toBeGreaterThan(before))
    container.remove()
  })

  it('自定义 containerId 生效（同页多面板不撞 id）', async () => {
    installSdk()
    const { container } = render(<SocialQrPanel provider={provider()} containerId="qr-panel-2" />)
    await waitFor(() => expect(document.getElementById('qr-panel-2')).toBeTruthy())
    container.remove()
  })
})

describe('SocialQrPanel：postMessage 双重校验（安全要点 1/2）', () => {
  it('origin 与 data 都通过时才跳转', async () => {
    installSdk()
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(document.getElementById('feishu-qr-container')).toBeTruthy())

    postScan({ tmp_code: 'CODE123' })
    await waitFor(() => expect(window.location.href).toContain('tmp_code=CODE123'))
    container.remove()
  })

  it('origin 校验失败时丢弃（防伪造登录结果）', async () => {
    installSdk({ matchOrigin: false })
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(document.getElementById('feishu-qr-container')).toBeTruthy())

    window.location.href = ''
    postScan({ tmp_code: 'EVIL' })
    await new Promise((r) => setTimeout(r, 50))
    expect(window.location.href).not.toContain('EVIL')
    container.remove()
  })

  it('data 校验失败时丢弃（防任意 iframe 冒充分享消息）', async () => {
    installSdk({ matchData: false })
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(document.getElementById('feishu-qr-container')).toBeTruthy())

    window.location.href = ''
    postScan({ tmp_code: 'EVIL' })
    await new Promise((r) => setTimeout(r, 50))
    expect(window.location.href).not.toContain('EVIL')
    container.remove()
  })

  it('SDK 校验方法抛异常时视为不可信（fail-closed）', async () => {
    installSdk({ throwOn: 'origin' })
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(document.getElementById('feishu-qr-container')).toBeTruthy())

    window.location.href = ''
    postScan({ tmp_code: 'EVIL' })
    await new Promise((r) => setTimeout(r, 50))
    expect(window.location.href).not.toContain('EVIL')
    container.remove()
  })

  it('缺少 tmp_code 或非字符串时不跳转', async () => {
    installSdk()
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(document.getElementById('feishu-qr-container')).toBeTruthy())

    window.location.href = ''
    postScan({})
    postScan({ tmp_code: 123 })
    postScan({ tmp_code: '' })
    await new Promise((r) => setTimeout(r, 50))
    expect(window.location.href).not.toContain('tmp_code')
    container.remove()
  })
})

describe('SocialQrPanel：tmp_code 拼接（安全要点 3）', () => {
  it('tmp_code 经 encodeURIComponent 后拼到 goto 上', async () => {
    installSdk()
    createSessionMock.mockResolvedValue({ goto: 'https://open.feishu.cn/auth?state=s1' })
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(document.getElementById('feishu-qr-container')).toBeTruthy())

    postScan({ tmp_code: 'a b&c=d/e' })
    await waitFor(() => expect(window.location.href).toContain('tmp_code='))
    // 特殊字符必须被转义
    expect(window.location.href).toContain('a%20b%26c%3Dd%2Fe')
    // 且是拼在 goto 上（保留原 state 参数）
    expect(window.location.href).toContain('state=s1')
    container.remove()
  })

  it('前端不把 tmp_code 当授权码单独使用（URL 上仍是 goto + tmp_code）', async () => {
    installSdk()
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(document.getElementById('feishu-qr-container')).toBeTruthy())

    postScan({ tmp_code: 'T1' })
    await waitFor(() => expect(window.location.href).toContain('tmp_code=T1'))
    expect(window.location.href).toContain('open.feishu.cn')
    container.remove()
  })
})

// ============ SDK 动态加载分支（覆盖率补测） ============

describe('SocialQrPanel：SDK 动态加载', () => {
  /** 拦截 script 插入，手动触发 onload / onerror */
  function spyScripts() {
    const original = document.head.appendChild.bind(document.head)
    let script: HTMLScriptElement | null = null
    const spy = vi.spyOn(document.head, 'appendChild').mockImplementation((node) => {
      if (node instanceof HTMLScriptElement) {
        script = node
        return node
      }
      return original(node)
    })
    return { spy, getScript: () => script }
  }

  it('window.QRLogin 已存在时不注入 script', async () => {
    installSdk()
    const { getScript } = spyScripts()
    const { container } = render(<SocialQrPanel provider={provider()} />)

    await waitFor(() => expect(createSessionMock).toHaveBeenCalled())
    expect(getScript()).toBeNull()
    container.remove()
  })

  it('script onload 且有 QRLogin 时 resolve 并渲染', async () => {
    const { getScript } = spyScripts()
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(createSessionMock).toHaveBeenCalled())
    await waitFor(() => expect(getScript()).toBeTruthy())

    // 模拟脚本加载完成：挂上 SDK 再触发 onload
    installSdk()
    await waitFor(() => {
      const s = getScript()!
      s.onload?.(new Event('load'))
      expect(document.getElementById('feishu-qr-container')).toBeTruthy()
    })
    container.remove()
  })

  it('script onerror 时进入错误态并提示检查网络', async () => {
    const { getScript } = spyScripts()
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(getScript()).toBeTruthy())

    await waitFor(() => {
      getScript()!.onerror?.(new Event('error'))
      expect(screen.getByRole('button', { name: /重新加载/ })).toBeTruthy()
    })
    container.remove()
  })

  it('加载失败后清掉全局缓存（重新加载才会真的重试）', async () => {
    const { getScript } = spyScripts()
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(getScript()).toBeTruthy())

    await waitFor(() => {
      getScript()!.onerror?.(new Event('error'))
      expect(screen.getByRole('button', { name: /重新加载/ })).toBeTruthy()
    })
    // rejected promise 不得永久挂载（否则重试永远拿到同一个 rejected promise）
    await waitFor(() => expect((window as unknown as { __feishuQrSdkLoading?: unknown }).__feishuQrSdkLoading).toBeUndefined())
    container.remove()
  })

  it('onload 但 QRLogin 仍未挂上：视为加载失败', async () => {
    const { getScript } = spyScripts()
    const { container } = render(<SocialQrPanel provider={provider()} />)
    await waitFor(() => expect(getScript()).toBeTruthy())

    await waitFor(() => {
      getScript()!.onload?.(new Event('load'))
      expect(screen.getByRole('button', { name: /重新加载/ })).toBeTruthy()
    })
    container.remove()
  })
})
