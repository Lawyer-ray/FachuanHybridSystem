/**
 * use-save-as 纯逻辑单测（node 环境）。
 *
 * `intentSubpath` 是「另存为」最容易悄悄坏掉的一环：后端按 source_path 逐字
 * 匹配编辑器会话，前端多 encode 或少 encode 一次都会变成「明明开着却报未打开」。
 * 这里锁定它与 `folderFileUrl` 同口径（编码后 URL 里的那份解码回来）。
 */
import { describe, expect, it } from 'vitest'

import { folderFileUrl } from '../../api'
import { canSaveAs, intentSubpath } from './use-save-as'

describe('canSaveAs', () => {
  it('合同文件夹的 docx 才可另存为', () => {
    expect(canSaveAs('contract', '顾问合同.docx')).toBe(true)
    expect(canSaveAs('contract', 'A.DOCX')).toBe(true)
  })

  it('非 docx 不可（只读 view 模式，改完存不回去）', () => {
    expect(canSaveAs('contract', '发票.pdf')).toBe(false)
    expect(canSaveAs('contract', 'docx.pdf')).toBe(false)
  })

  it('案件文件夹不可（后端只有 contracts 侧有该端点）', () => {
    expect(canSaveAs('case', '起诉状.docx')).toBe(false)
  })
})

describe('intentSubpath', () => {
  it('还原出已解码一次的原文（与 folderFileUrl 编码口径一致）', () => {
    expect(intentSubpath('contract', 318, '1-合同/a.docx')).toBe('1-合同/a.docx')
    expect(folderFileUrl('contract', 318, '1-合同/a.docx')).toContain(
      'subpath=' + encodeURIComponent('1-合同/a.docx'),
    )
  })

  it('空格、& 等 query 敏感字符同样还原（只解码一次，不吃二次解码）', () => {
    expect(intentSubpath('contract', 9, 'dir/a b&c.docx')).toBe('dir/a b&c.docx')
    expect(intentSubpath('case', 5, 'dir/100%.docx')).toBe('dir/100%.docx')
  })
})
