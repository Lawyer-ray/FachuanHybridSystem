import { describe, expect, it } from 'vitest'

import { MATERIAL_MAX_BYTES, formatSize, mergeFiles, rejectionReason } from './material-files'

/** 造一个受支持的小 PDF File（node 环境有 File，无需 DOM） */
function pdf(name = '判决书.pdf', size = 1024, lastModified = 1): File {
  return new File([new Uint8Array(size)], name, { type: 'application/pdf', lastModified })
}

describe('rejectionReason', () => {
  it('接受 PDF / Word / 图片', () => {
    for (const name of ['a.pdf', 'b.DOC', 'c.docx', 'd.JPG', 'e.png', 'f.bmp']) {
      expect(rejectionReason(pdf(name))).toBeNull()
    }
  })

  it('拒绝不支持的扩展名', () => {
    expect(rejectionReason(new File(['x'], '录屏.mov'))).toBe('格式不支持')
    expect(rejectionReason(new File(['x'], '微信图片.heic'))).toBe('格式不支持')
  })

  it('拒绝超过 50MB 的文件', () => {
    const big = pdf('巨大扫描件.pdf', MATERIAL_MAX_BYTES + 1)
    expect(rejectionReason(big)).toBe('超过 50MB')
  })

  it('恰好 50MB 仍可接受（边界含等号）', () => {
    expect(rejectionReason(pdf('刚好.pdf', MATERIAL_MAX_BYTES))).toBeNull()
  })
})

describe('mergeFiles', () => {
  it('并入新文件并保持顺序', () => {
    const first = pdf('a.pdf', 10, 1)
    const second = pdf('b.pdf', 20, 2)

    const { next, rejected } = mergeFiles([first], [second])

    expect(next).toEqual([first, second])
    expect(rejected).toEqual([])
  })

  it('同名同大小同修改时间的重复文件被去重', () => {
    const file = pdf('判决书.pdf', 100, 500)

    const { next } = mergeFiles([file], [pdf('判决书.pdf', 100, 500)])

    expect(next).toHaveLength(1)
  })

  it('同名但内容不同（大小不同）视为两个文件', () => {
    const { next } = mergeFiles([pdf('扫描.pdf', 100, 500)], [pdf('扫描.pdf', 200, 500)])

    expect(next).toHaveLength(2)
  })

  it('不合规文件进 rejected 且不进列表', () => {
    const good = pdf('ok.pdf')
    const bad = new File(['x'], 'x.heic')

    const { next, rejected } = mergeFiles([], [good, bad])

    expect(next).toEqual([good])
    expect(rejected).toEqual([{ name: 'x.heic', reason: '格式不支持' }])
  })

  it('空输入时内容不变（调用方用长度判是否更新）', () => {
    const prev = [pdf('a.pdf')]
    const { next, rejected } = mergeFiles(prev, [])

    expect(next).toStrictEqual(prev)
    expect(rejected).toEqual([])
  })
})

describe('formatSize', () => {
  it('按量级选单位', () => {
    expect(formatSize(512)).toBe('512 B')
    expect(formatSize(2048)).toBe('2 KB')
    expect(formatSize(5 * 1024 * 1024)).toBe('5.0 MB')
  })
})
