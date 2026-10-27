import { describe, expect, it } from 'vitest'

import { formatFileSize, splitAttachmentFiles, validateAttachmentFile } from './attachment'

/** 只带 name/size 的最小 File 替身（node 环境无真实 File，分拣逻辑只看这两个字段） */
const asFile = (name: string, size: number) => ({ name, size }) as File

describe('附件预检（P1-11）', () => {
  it('validateAttachmentFile：白名单/限额/空文件', () => {
    expect(validateAttachmentFile({ name: '合同.PDF', size: 100 })).toBeNull()
    expect(validateAttachmentFile({ name: '图.JPG', size: 100 })).toBeNull()
    expect(validateAttachmentFile({ name: 'a.exe', size: 1 })).toContain('不支持的格式')
    expect(validateAttachmentFile({ name: 'a.txt', size: 21 * 1024 * 1024 })).toContain('20MB')
    expect(validateAttachmentFile({ name: 'a.txt', size: 0 })).toContain('文件为空')
  })

  it('formatFileSize：B/KB/MB（口径收敛到 lib/format 的 formatBytes）', () => {
    expect(formatFileSize(500)).toBe('500B')
    expect(formatFileSize(2048)).toBe('2KB')
    expect(formatFileSize(3 * 1024 * 1024)).toBe('3.0MB')
    // 收敛后两个修正点：1MB 前一档升档、GB 档不再显示成「1536.0MB」
    expect(formatFileSize(1024 * 1024 - 1)).toBe('1.0MB')
    expect(formatFileSize(1.5 * 1024 ** 3)).toBe('1.5GB')
  })

  it('splitAttachmentFiles：合规与拒绝分拣，拒绝项带「文件名」+原因', () => {
    const { accepted, rejected } = splitAttachmentFiles([
      asFile('合同.pdf', 100),
      asFile('病毒.exe', 100),
      asFile('空.txt', 0),
    ])
    expect(accepted.map((f) => f.name)).toEqual(['合同.pdf'])
    expect(rejected).toHaveLength(2)
    expect(rejected[0]).toContain('「病毒.exe」')
    expect(rejected[0]).toContain('不支持的格式')
    expect(rejected[1]).toContain('「空.txt」')
  })
})
