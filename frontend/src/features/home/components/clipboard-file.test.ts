import { fileFromClipboard, normalizePastedFile } from './clipboard-file'

/**
 * 剪贴板文件提取 / 泛名补扩展名的单测。
 *
 * 为什么值得测：recognize 端点按文件名后缀校验，浏览器给粘贴图片的泛名
 * （image.png / blob）不改名就会被后端整单拒收；改名规则写错（比如把用户
 * 从 Finder 复制的真实文件名也改掉）又会弄丢信息量。
 */

const NOW = new Date(2026, 9, 18, 10, 30, 5)

function makeFile(name: string, type = '', parts: BlobPart[] = ['x']): File {
  return new File(parts, name, { type })
}

describe('normalizePastedFile', () => {
  it('浏览器占位名 image.png 按时间戳重命名', () => {
    const out = normalizePastedFile(makeFile('image.png', 'image/png'), NOW)
    expect(out.name).toBe('粘贴图片-20261018-103005.png')
    expect(out.type).toBe('image/png')
  })

  it('无扩展名的 blob 按 MIME 补 .png', () => {
    expect(normalizePastedFile(makeFile('blob', 'image/png'), NOW).name).toBe('粘贴图片-20261018-103005.png')
  })

  it('image/jpeg 统一落 .jpg；白名单外的 MIME 也照实落扩展名，好让校验报出具体格式', () => {
    expect(normalizePastedFile(makeFile('image.jpeg', 'image/jpeg'), NOW).name).toBe('粘贴图片-20261018-103005.jpg')
    expect(normalizePastedFile(makeFile('blob', 'image/webp'), NOW).name).toBe('粘贴图片-20261018-103005.webp')
  })

  it('名字有信息量的原样保留（Finder 复制的真实文件）', () => {
    const f = makeFile('传票.pdf', 'application/pdf')
    expect(normalizePastedFile(f, NOW)).toBe(f)
  })

  it('未知 MIME 且无扩展名：改不动就原样保留，交 fileRejectReason 报格式', () => {
    const f = makeFile('blob')
    expect(normalizePastedFile(f, NOW)).toBe(f)
  })
})

describe('fileFromClipboard', () => {
  it('files 里直接有文件：取第一个并归一化', () => {
    const f = fileFromClipboard({ files: [makeFile('image.png', 'image/png')] }, NOW)
    expect(f?.name).toBe('粘贴图片-20261018-103005.png')
  })

  it('files 为空时兜底 items 里 kind=file 的项', () => {
    const inner = makeFile('image.png', 'image/png')
    const f = fileFromClipboard(
      { items: [{ kind: 'string', getAsFile: () => null }, { kind: 'file', getAsFile: () => inner }] },
      NOW,
    )
    expect(f?.name).toBe('粘贴图片-20261018-103005.png')
  })

  it('纯文字剪贴板（无 files / items）返回 null，不拦截默认粘贴', () => {
    expect(fileFromClipboard(null)).toBeNull()
    expect(fileFromClipboard({ files: [], items: [] })).toBeNull()
  })

  it('items 里声明了 file 但 getAsFile 给 null：跳过继续找', () => {
    const inner = makeFile('a.pdf', 'application/pdf')
    const f = fileFromClipboard({
      items: [{ kind: 'file', getAsFile: () => null }, { kind: 'file', getAsFile: () => inner }],
    })
    expect(f?.name).toBe('a.pdf')
  })
})
