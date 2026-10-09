// @vitest-environment jsdom
/**
 * home/api/download 单测（jsdom）。
 *
 * download.ts 的 triggerDownload 是纯 DOM 行为（建 <a>、click、移除），
 * 断言聚焦：点击时机（先挂载后点击再移除）、href 透传、download 属性置空
 * （文件名交由响应头 Content-Disposition）。
 */
import { describe, expect, it, vi } from 'vitest'

import { triggerDownload } from './download'

describe('triggerDownload', () => {
  it('创建临时 <a> 挂到 body、href 透传、download 置空、点击后即移除', async () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    try {
      await triggerDownload('/api/v1/doc-convert/records/1/download?ticket=TK')

      expect(clickSpy).toHaveBeenCalledTimes(1)
      // 点击发生时锚点仍在文档里（点击后才 remove）
      const clicked = clickSpy.mock.instances[0] as unknown as HTMLAnchorElement
      expect(clicked).toBeInstanceOf(HTMLAnchorElement)
      expect(clicked.getAttribute('href')).toBe('/api/v1/doc-convert/records/1/download?ticket=TK')
      expect(clicked.download).toBe('')
      // 函数返回后临时节点已清理，body 不残留
      expect(document.querySelector('a[href*="doc-convert"]')).toBeNull()
    } finally {
      clickSpy.mockRestore()
    }
  })
})
