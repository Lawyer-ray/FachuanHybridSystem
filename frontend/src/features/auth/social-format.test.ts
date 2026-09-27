import { describe, expect, it } from 'vitest'
import { spacedBrand } from './social-format'

describe('spacedBrand', () => {
  it('拉丁品牌两侧补空格', () => {
    expect(spacedBrand('使用', 'Google', '登录')).toBe('使用 Google 登录')
    expect(spacedBrand('将跳转到', 'Google', '完成授权')).toBe('将跳转到 Google 完成授权')
  })

  it('中文品牌紧贴，不留空格', () => {
    expect(spacedBrand('使用', '飞书', '登录')).toBe('使用飞书登录')
    expect(spacedBrand('使用', '微信', '登录')).toBe('使用微信登录')
  })

  it('数字开头的品牌按拉丁处理', () => {
    expect(spacedBrand('使用', '360', '登录')).toBe('使用 360 登录')
  })

  it('空品牌名不产生多余空格', () => {
    expect(spacedBrand('使用', '', '登录')).toBe('使用登录')
  })
})
