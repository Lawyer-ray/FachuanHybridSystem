import { describe, expect, it } from 'vitest'

import { shortDocName, splitLinkText } from './filename-text'

describe('shortDocName 附件短名', () => {
  it('去扩展名 + 第一个下划线起的尾巴（生成文书的委托人后缀）', () => {
    expect(shortDocName('民事诉讼风险提示书_test_某某示范公司.pdf')).toBe('民事诉讼风险提示书')
    expect(shortDocName('传票_test_某某示范公司.docx')).toBe('传票')
  })
  it('无下划线只去扩展名；无扩展名原样', () => {
    expect(shortDocName('起诉状.txt')).toBe('起诉状')
    expect(shortDocName('会议纪要')).toBe('会议纪要')
  })
  it('以 _ 开头（截断后为空）回退全名，不让 chip 变空', () => {
    expect(shortDocName('_副本.pdf')).toBe('_副本.pdf')
  })
})

describe('splitLinkText 日志正文链接切分', () => {
  it('法院短信：URL 成段，前后的中文（含紧跟链接的文字）不被吞进 URL', () => {
    const text = '你好，请查收送达文书。点击链接查阅：https://zxfw.court.gov.cn/zxfw/#/index?qdbh=abc123&sdsin=def456请及时查收，逾期视为送达'
    const segs = splitLinkText(text)
    expect(segs[0]).toEqual({ kind: 'text', value: '你好，请查收送达文书。点击链接查阅：' })
    expect(segs[1]?.kind).toBe('url')
    expect(segs[1]?.value).toBe('https://zxfw.court.gov.cn/zxfw/#/index?qdbh=abc123&sdsin=def456')
    expect(segs[2]).toEqual({ kind: 'text', value: '请及时查收，逾期视为送达' })
  })
  it('多个 URL 逐段切开', () => {
    const segs = splitLinkText('先看 https://a.com/x 再看 http://b.com/y')
    expect(segs).toEqual([
      { kind: 'text', value: '先看 ' },
      { kind: 'url', value: 'https://a.com/x' },
      { kind: 'text', value: ' 再看 ' },
      { kind: 'url', value: 'http://b.com/y' },
    ])
  })
  it('无 URL 时整段文本', () => {
    expect(splitLinkText('普通日志，无链接')).toEqual([{ kind: 'text', value: '普通日志，无链接' }])
  })
})
