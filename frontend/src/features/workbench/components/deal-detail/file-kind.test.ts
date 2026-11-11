/**
 * file-kind：扩展名 → 渲染分类（纯函数，node 环境）。
 *
 * 分类口径跟着渲染走：每类一套颜色标识，认不出的统一 other（仍可点、可下载）。
 */
import { describe, expect, it } from 'vitest'

import { kindOf } from './file-kind'

describe('kindOf：扩展名分类', () => {
  it('pdf 单独一类', () => {
    expect(kindOf('起诉状.pdf')).toBe('pdf')
    expect(kindOf('起诉状.PDF')).toBe('pdf')
  })

  it('word 家族含 doc/docx/dotx/wps/rtf/odt', () => {
    for (const ext of ['doc', 'docx', 'dotx', 'wps', 'rtf', 'odt']) {
      expect(kindOf(`《股东协议》.${ext}`)).toBe('word')
    }
  })

  it('表格家族含 xls/xlsx/xlsm/csv/et', () => {
    for (const ext of ['xls', 'xlsx', 'xlsm', 'csv', 'et']) {
      expect(kindOf(`对账表.${ext}`)).toBe('sheet')
    }
  })

  it('图片家族含 png/jpg/jpeg/gif/webp/bmp/tif/tiff', () => {
    for (const ext of ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tif', 'tiff']) {
      expect(kindOf(`回单.${ext}`)).toBe('image')
    }
  })

  it('大小写不敏感', () => {
    expect(kindOf('起诉状.DOCX')).toBe('word')
    expect(kindOf('回单.JPeG')).toBe('image')
  })

  it('无扩展名与未知扩展名都归 other', () => {
    expect(kindOf('README')).toBe('other')
    expect(kindOf('归档.zip')).toBe('other')
    expect(kindOf('')).toBe('other')
  })

  it('取最后一个点之后的后缀（多段文件名）', () => {
    expect(kindOf('租赁合同.v2.final.docx')).toBe('word')
    expect(kindOf('租赁合同.tar.pdf')).toBe('pdf')
  })

  it('隐藏文件与结尾带点的名字不误判', () => {
    expect(kindOf('.DS_Store')).toBe('other')
    expect(kindOf('归档.')).toBe('other')
  })
})
