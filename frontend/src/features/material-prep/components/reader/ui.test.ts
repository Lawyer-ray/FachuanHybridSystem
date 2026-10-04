/**
 * reader/ui.ts 取字拖框判定纯函数单测（node 环境）。
 *
 * 回归背景：PageCell 曾对任意 1px 位移都记录矩形，pointerup 时
 * 「有矩形但未超阈值」两个分支都不进，形成点击死区；判定收敛到
 * resolveDragRect 后，阈值内位移必须恒为 null（走记页码）。
 */
import { describe, expect, it } from 'vitest'

import { resolveDragRect } from './ui'

describe('resolveDragRect 拖框判定', () => {
  it('无位移（原点点击）：null', () => {
    expect(resolveDragRect({ x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 })).toBeNull()
  })

  it('位移 0.5%（阈值内手抖）：null —— 修复前的点击死区', () => {
    expect(resolveDragRect({ x: 0.5, y: 0.5 }, { x: 0.505, y: 0.5 })).toBeNull()
    expect(resolveDragRect({ x: 0.5, y: 0.5 }, { x: 0.5, y: 0.505 })).toBeNull()
  })

  it('位移恰等于阈值：仍为 null（严格大于才算拖框）', () => {
    // 用 1/64（0.015625）做「恰好低于阈值」的精确位移，避开浮点误差
    expect(resolveDragRect({ x: 0.5, y: 0.5 }, { x: 0.515625, y: 0.5 })).toBeNull()
  })

  it('超阈值位移（横向 1/4）：返回左上角归一化矩形', () => {
    // 0.25 / 0.125 均为二进制精确值，断言无浮点噪声
    expect(resolveDragRect({ x: 0.5, y: 0.5 }, { x: 0.75, y: 0.625 })).toEqual({
      x: 0.5,
      y: 0.5,
      w: 0.25,
      h: 0.125,
    })
  })

  it('仅纵向超阈值：也构成拖框', () => {
    const rect = resolveDragRect({ x: 0.3, y: 0.2 }, { x: 0.3, y: 0.9 })
    expect(rect).toEqual({ x: 0.3, y: 0.2, w: 0, h: 0.7 })
  })

  it('反向拖（往左上）：矩形仍归一化为正宽高', () => {
    expect(resolveDragRect({ x: 0.75, y: 0.625 }, { x: 0.25, y: 0.125 })).toEqual({
      x: 0.25,
      y: 0.125,
      w: 0.5,
      h: 0.5,
    })
  })

  it('超阈值后缩回阈值内：回到 null（拖框取消，pointerup 记页码）', () => {
    const a = { x: 0.5, y: 0.5 }
    expect(resolveDragRect(a, { x: 0.9, y: 0.9 })).not.toBeNull()
    expect(resolveDragRect(a, { x: 0.505, y: 0.505 })).toBeNull()
  })
})
