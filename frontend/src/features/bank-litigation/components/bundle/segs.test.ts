/**
 * 整包分段的两块纯逻辑单测（node 环境：Node 22 的 Blob 自带 .stream()，
 * 与浏览器行为一致；jsdom 的 Blob 缺 stream()，放那边要手工补原型）。
 *
 * guessSide 决定材料归「我方 / 对方」—— 判错只是标签错，**留空会被后端硬校验拦住**，
 * 所以规则故意保守（拿不准算我方）。这里逐一钉住它的分支。
 *
 * unzipToFiles 是后端导出 zip 的解析器：手写中央目录解析 + DecompressionStream。
 * 用真 zip 字节来测（store 与 deflate 两条路径都走），
 * 否则「导入归案」在真实整包上会静默少文件。
 */
import { describe, expect, it } from 'vitest'

import type { PdfSplitSegment } from '../../api'
import { guessSide, unzipToFiles } from './segs'

/** 只填 guessSide 用得到的字段，其余按 SegmentOut 可选置空 */
function seg(filename: string, segmentLabel?: string | null): PdfSplitSegment {
  return {
    page_start: 1,
    page_end: 1,
    segment_type: 'other',
    filename,
    segment_label: segmentLabel ?? null,
  } as PdfSplitSegment
}

describe('guessSide', () => {
  it('文件名同时带了对方当事人与对方文书类型，判对方', () => {
    expect(guessSide(seg('被告张某身份证.pdf'))).toBe('opponent')
    expect(guessSide(seg('被上诉人李某答辩状.pdf'))).toBe('opponent')
    expect(guessSide(seg('被申请人某公司上诉状.pdf'))).toBe('opponent')
    expect(guessSide(seg('对方王某身份证明.pdf'))).toBe('opponent')
  })

  it('「被告」开头且是 pdf 的整份文件判对方（规则二）', () => {
    // 规则二不看文书类型，只看开头当事人 + 后缀
    expect(guessSide(seg('被告陈某材料.PDF'))).toBe('opponent')
  })

  it('标签里写明了对方当事人与文书类型，文件名看不出来也能判对方', () => {
    // 匹配串是 `${filename} ${segment_label}`，所以标签参与匹配
    expect(guessSide(seg('05_材料.pdf', '被告身份证扫描件'))).toBe('opponent')
  })

  it('对方当事人但没有对方文书类型 —— 规则一不命中，回落我方（不走规则二的一大或其他非 pdf 后缀）', () => {
    // 规则一要求「当事人 + 文书类型」同时出现；只有当事人不算证据
    // 这里是「被告」在开头但后缀不是 .pdf，规则二也不命中
    expect(guessSide(seg('被告张某还款流水.jpg'))).toBe('our')
    // 注意：「被告xxx.pdf」这类**开头当事人 + pdf** 的整份文件走规则二，见下一条
  })

  it('我方材料（起诉状 / 借款合同 / 空名）一律判我方', () => {
    expect(guessSide(seg('01_民事起诉状.pdf'))).toBe('our')
    expect(guessSide(seg('06_借款合同.pdf'))).toBe('our')
    expect(guessSide(seg(''))).toBe('our')
  })

  it('「被告」不在文件名开头时规则二不生效（仍按有无对方文书类型判）', () => {
    // 规则二的锚点是 ^：文件中段出现的「被告」不算
    expect(guessSide(seg('材料_被告张三.pdf'))).toBe('our')
    expect(guessSide(seg('材料_被告张三答辩状.pdf'))).toBe('opponent')
  })

  it('规则二比规则一宽：开头是对方当事人 + pdf，不看文书类型也判对方', () => {
    // 这是有意的口径：整份文件命名以对方当事人开头，说明就是对方的卷
    expect(guessSide(seg('被告张某还款流水.pdf'))).toBe('opponent')
  })

  it('segment_label 为 null / undefined 不影响判定', () => {
    expect(guessSide(seg('03_当事人身份证明.pdf', null))).toBe('our')
    // 类型上 segment_label 必填（生成物不标 optional），但后端可能漏字段；
    // 用断言的 undefined 探真值兜底路径（`?? ''`）。
    expect(guessSide({ ...seg('x.pdf'), segment_label: undefined as unknown as string })).toBe('our')
  })
})

// ───────────────────────── zip 构造 ─────────────────────────

interface ZipInput {
  name: string
  data: Uint8Array
  /** 0 = store，8 = deflate-raw */
  method: number
}

/** 压 deflate-raw（zip 的 method 8 就是这个算法） */
async function deflateRaw(data: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([toBlobPart(data)]).stream().pipeThrough(new CompressionStream('deflate-raw'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

/** Uint8Array 转 BlobPart：TS 6 下 Uint8Array<ArrayBufferLike> 不直接兼容 BlobPart */
function toBlobPart(data: Uint8Array): BlobPart {
  const copy = new Uint8Array(data.length)
  copy.set(data)
  return copy.buffer
}

/**
 * 手工拼一个最小 zip（每个条目：本地头 + 数据；末尾：中央目录 + EOCD）。
 *
 * 不用第三方库：被测代码就是手写解析器，用同一套字节布局拼出来
 * 才能验证它读的偏移是否对得上（用别人的库拼容易「两个 bug 互相抵消」）。
 */
async function buildZip(entries: ZipInput[]): Promise<Uint8Array> {
  const enc = new TextEncoder()
  const locals: Uint8Array[] = []
  const centrals: Uint8Array[] = []
  let offset = 0

  for (const e of entries) {
    const nameBytes = enc.encode(e.name)
    const payload = e.method === 8 ? await deflateRaw(e.data) : e.data

    const local = new Uint8Array(30 + nameBytes.length + payload.length)
    const lv = new DataView(local.buffer)
    lv.setUint32(0, 0x04034b50, true) // 本地头签名
    lv.setUint16(8, e.method, true) // 压缩方式
    lv.setUint32(18, payload.length, true) // 压缩后大小
    lv.setUint32(22, e.data.length, true) // 原始大小
    lv.setUint16(26, nameBytes.length, true) // 文件名长度
    lv.setUint16(28, 0, true) // extra 长度
    local.set(nameBytes, 30)
    local.set(payload, 30 + nameBytes.length)
    locals.push(local)

    const central = new Uint8Array(46 + nameBytes.length)
    const cv = new DataView(central.buffer)
    cv.setUint32(0, 0x02014b50, true) // 中央目录签名
    cv.setUint16(10, e.method, true)
    cv.setUint32(20, payload.length, true)
    cv.setUint32(24, e.data.length, true)
    cv.setUint16(28, nameBytes.length, true)
    cv.setUint16(30, 0, true) // extra
    cv.setUint16(32, 0, true) // comment
    cv.setUint32(42, offset, true) // 本地头偏移
    central.set(nameBytes, 46)
    centrals.push(central)

    offset += local.length
  }

  const centralSize = centrals.reduce((s, c) => s + c.length, 0)
  const eocd = new Uint8Array(22)
  const ev = new DataView(eocd.buffer)
  ev.setUint32(0, 0x06054b50, true) // EOCD 签名
  ev.setUint16(8, entries.length, true) // 本盘条目数
  ev.setUint16(10, entries.length, true) // 总条目数
  ev.setUint32(12, centralSize, true) // 中央目录大小
  ev.setUint32(16, offset, true) // 中央目录偏移

  const out = new Uint8Array(offset + centralSize + eocd.length)
  let p = 0
  for (const l of locals) {
    out.set(l, p)
    p += l.length
  }
  for (const c of centrals) {
    out.set(c, p)
    p += c.length
  }
  out.set(eocd, p)
  return out
}

function blobOf(bytes: Uint8Array): Blob {
  return new Blob([toBlobPart(bytes)])
}

const enc = new TextEncoder()

describe('unzipToFiles', () => {
  it('store 条目直接切出来；文件名取 basename 并统一标成 application/pdf', async () => {
    const zip = await buildZip([{ name: 'out/01_民事起诉状.pdf', data: enc.encode('%PDF-1'), method: 0 }])
    const files = await unzipToFiles(blobOf(zip))

    expect(files).toHaveLength(1)
    expect(files[0]!.name).toBe('01_民事起诉状.pdf')
    expect(files[0]!.type).toBe('application/pdf')
    expect(await files[0]!.text()).toBe('%PDF-1')
  })

  it('deflate 条目走 DecompressionStream 解压，内容与原文一致', async () => {
    const body = enc.encode('%PDF-1.7 ' + 'A'.repeat(2000))
    const zip = await buildZip([{ name: '02_借款合同.pdf', data: body, method: 8 }])
    const files = await unzipToFiles(blobOf(zip))

    expect(files).toHaveLength(1)
    expect(files[0]!.name).toBe('02_借款合同.pdf')
    expect(await files[0]!.text()).toBe(new TextDecoder().decode(body))
  })

  it('目录条目（名字以 / 结尾）被跳过，只返回真文件', async () => {
    const zip = await buildZip([
      { name: 'out/', data: new Uint8Array(0), method: 0 },
      { name: 'out/a.pdf', data: enc.encode('A'), method: 0 },
      { name: 'out/b.pdf', data: enc.encode('B'), method: 8 },
    ])
    const files = await unzipToFiles(blobOf(zip))

    expect(files.map((f) => f.name)).toEqual(['a.pdf', 'b.pdf'])
  })

  it('不支持的压缩方式（如 bzip2 = 12）被跳过，不会产出空文件', async () => {
    const zip = await buildZip([
      { name: 'a.pdf', data: enc.encode('A'), method: 0 },
      // method 12 不在支持列表里：inflateEntry 返回 null
      { name: 'b.pdf', data: enc.encode('B'), method: 12 },
    ])
    const files = await unzipToFiles(blobOf(zip))

    expect(files.map((f) => f.name)).toEqual(['a.pdf'])
  })

  it('不是 zip 的字节（找不到 EOCD）返回空数组，不抛错', async () => {
    const garbage = new Uint8Array(64).fill(0x41)
    await expect(unzipToFiles(blobOf(garbage))).resolves.toEqual([])
  })

  it('空 zip（0 个条目）返回空数组', async () => {
    const zip = await buildZip([])
    await expect(unzipToFiles(blobOf(zip))).resolves.toEqual([])
  })

  it('文件名不含目录前缀时原样保留（split 的兜底分支）', async () => {
    const zip = await buildZip([{ name: '03_证据清单.pdf', data: enc.encode('C'), method: 0 }])
    const files = await unzipToFiles(blobOf(zip))
    expect(files[0]!.name).toBe('03_证据清单.pdf')
  })
})
