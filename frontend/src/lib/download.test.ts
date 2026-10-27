// @vitest-environment jsdom
/**
 * lib/download（saveBlob / downloadUrl）单测。
 *
 * 核心契约：blob 下载用完必须 revoke——收敛前 5 处手写副本全都漏了，
 * 每下载一次就泄漏一份 Blob 内存。这里锁住「revoke 确实发生、且发生在
 * click 之后（延到下一个宏任务）」以及「直链下载不创建 ObjectURL」。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { downloadUrl, saveBlob } from './download'

/** 记录被点击的 <a>：href / download 属性 + 点击时它是否还在 DOM 里 */
interface Clicked {
  href: string
  download: string | null
  rel: string
  inDomAtClick: boolean
}

let clicked: Clicked[]
let createObjectURL: ReturnType<typeof vi.fn>
let revokeObjectURL: ReturnType<typeof vi.fn>

beforeEach(() => {
  clicked = []
  let seq = 0
  createObjectURL = vi.fn(() => `blob:fake-${seq++}`)
  revokeObjectURL = vi.fn()
  URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL
  URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL
  // jsdom 对未挂载/无 href 的 a 点击会走导航告警，这里拦下 click 记录行为
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push({
      href: this.getAttribute('href') ?? '',
      download: this.getAttribute('download'),
      rel: this.getAttribute('rel') ?? '',
      inDomAtClick: document.body.contains(this),
    })
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  // 清掉可能残留的宏任务回调
  document.body.innerHTML = ''
})

describe('saveBlob', () => {
  it('创建 ObjectURL → 点击带 download 的 a → 下一个宏任务 revoke', () => {
    vi.useFakeTimers()
    const blob = new Blob(['hello'], { type: 'text/plain' })

    saveBlob(blob, '起诉状.txt')

    expect(createObjectURL).toHaveBeenCalledWith(blob)
    expect(clicked).toHaveLength(1)
    expect(clicked[0]).toMatchObject({
      href: 'blob:fake-0',
      download: '起诉状.txt',
      rel: 'noopener',
      inDomAtClick: true, // 点的时候必须已挂在 body 上，否则部分浏览器不触发下载
    })
    // 点完的 a 立即摘除，不留 DOM 残渣
    expect(document.querySelector('a')).toBeNull()
    // 同步就 revoke 会让 Firefox 取不到数据，必须延到宏任务
    expect(revokeObjectURL).not.toHaveBeenCalled()

    vi.runAllTimers()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake-0')
  })

  it('两次下载各自回收自己的 URL', () => {
    vi.useFakeTimers()
    saveBlob(new Blob(['a']), 'a.txt')
    saveBlob(new Blob(['b']), 'b.txt')
    vi.runAllTimers()
    expect(revokeObjectURL.mock.calls.map((c) => c[0])).toEqual(['blob:fake-0', 'blob:fake-1'])
  })
})

describe('downloadUrl', () => {
  it('直链下载不创建 ObjectURL，filename 省略时不设 download（交给响应头）', () => {
    downloadUrl('/api/v1/files/7?ticket=abc')
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(clicked).toHaveLength(1)
    expect(clicked[0]).toMatchObject({
      href: '/api/v1/files/7?ticket=abc',
      download: null,
      rel: 'noopener',
      inDomAtClick: true,
    })
    expect(revokeObjectURL).not.toHaveBeenCalled()
  })

  it('给了 filename 则设 download 属性', () => {
    downloadUrl('/media/x/合同.pdf', '合同.pdf')
    expect(clicked[0]?.download).toBe('合同.pdf')
  })
})
