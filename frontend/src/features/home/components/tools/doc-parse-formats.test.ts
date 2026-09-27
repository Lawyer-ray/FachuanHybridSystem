import { BACKEND_FORMATS, FORMAT_HINT, extOf, acceptOf, rejectReason, sizeReason, MAX_PARSE_FILE_BYTES } from './doc-parse-formats'

/**
 * 格式校验表 / 校验函数的单测。
 *
 * 为什么值得测：BACKEND_FORMATS 是从后端 backends/*.py 的 get_supported_formats
 * 抄过来的镜像，抄漏/抄错一个扩展名，前端就会放过一个后端必然拒收的文件
 * （或拦掉本来能用的文件）。这里把「auto 是各云端后端并集」这类易错口径钉死。
 */
describe('extOf', () => {
  it('取小写扩展名，不含点', () => {
    expect(extOf('合同.PDF')).toBe('pdf')
    expect(extOf('a.b.docx')).toBe('docx')
  })

  it('无扩展名或以点开头时返回空串', () => {
    expect(extOf('README')).toBe('')
    expect(extOf('.gitignore')).toBe('')
  })
})

describe('rejectReason', () => {
  it('后端支持该格式时放行（返回 null）', () => {
    expect(rejectReason('判决书.pdf', 'mineru')).toBeNull()
    expect(rejectReason('数据.csv', 'textin')).toBeNull()
  })

  it('local 后端只吃 PDF 与图片，拒 Word / OFD', () => {
    expect(rejectReason('合同.docx', 'local')).toContain('docx')
    expect(rejectReason('章.ofd', 'local')).toContain('ofd')
    expect(rejectReason('扫描件.jpg', 'local')).toBeNull()
  })

  it('MinerU 不收 OFD / RTF / HTML（TextinParse 才收）', () => {
    expect(rejectReason('章.ofd', 'mineru')).toContain('ofd')
    expect(rejectReason('章.ofd', 'textin')).toBeNull()
  })

  it('没扩展名给明确原因，不放行', () => {
    expect(rejectReason('合同', 'textin')).toContain('扩展名')
  })

  it('auto 覆盖各云端后端并集——任一端点支持即可', () => {
    // MinerU 独有的 jpg 与 TextinParse 独有的 ofd，auto 都应放行
    expect(rejectReason('a.jpg', 'auto')).toBeNull()
    expect(rejectReason('a.ofd', 'auto')).toBeNull()
    // 两边都不支持的也不放行
    expect(rejectReason('a.zip', 'auto')).toContain('zip')
  })
})

describe('格式表一致性', () => {
  it('auto 恰为 mineru 与 textin 的并集（不多不少）', () => {
    const union = new Set([...BACKEND_FORMATS.mineru, ...BACKEND_FORMATS.textin])
    expect(new Set(BACKEND_FORMATS.auto)).toEqual(union)
  })

  it('每个后端都有展示文案，且非空', () => {
    for (const key of Object.keys(BACKEND_FORMATS) as (keyof typeof BACKEND_FORMATS)[]) {
      expect(FORMAT_HINT[key]).toBeTruthy()
    }
  })

  it('accept 字符串以点开头且覆盖全部格式', () => {
    const accept = acceptOf('local')
    expect(accept.startsWith('.pdf,')).toBe(true)
    for (const ext of BACKEND_FORMATS.local) {
      expect(accept).toContain(`.${ext}`)
    }
  })
})

describe('sizeReason', () => {
  it('未超限返回 null', () => {
    expect(sizeReason(MAX_PARSE_FILE_BYTES)).toBeNull()
    expect(sizeReason(0)).toBeNull()
  })

  it('超限给提示', () => {
    expect(sizeReason(MAX_PARSE_FILE_BYTES + 1)).toContain('100MB')
  })
})
