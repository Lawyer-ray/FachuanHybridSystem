/**
 * 页旋转纯函数（node 环境）。
 *
 * 这些函数是「人工转正」的地基，错了不会被构建拦住，只会让律师看到：
 * 转了但看着没转、框指到隔壁、归案上传的还是歪的、已旋转计数不对。所以每条
 * 边界都按后果写断言：
 *
 * 1. 角度收敛（pdf.js 对非 90 倍数直接抛错）；
 * 2. 转四次 90° 回到「没转过」，且草稿里不留 `{k:0}` 噪音（否则计数会骗人）；
 * 3. 归一化矩形换算在四种角度下都对（引擎框/OCR 框跟着页转）；
 * 4. 给后端的编码只含区间内非 0 的页、按页码升序（后端按页号查表）。
 */
import { describe, expect, it } from 'vitest'

import type { PageRotMap } from '../types'
import {
  countRotated,
  getPageRot,
  normalizeDeg,
  pageRotKey,
  parsePageRotKey,
  resetRefsRotation,
  rotateNormRect,
  rotateRefs,
  rotatedRefsOf,
  rotatedSizeOf,
  rotationsForRange,
  setRefsRotation,
} from './page-rotation'

const R = (partIndex: number, page: number) => ({ partIndex, page })
const closeRect = (a: { x: number; y: number; w: number; h: number }, b: typeof a) => {
  expect(a.x).toBeCloseTo(b.x, 6)
  expect(a.y).toBeCloseTo(b.y, 6)
  expect(a.w).toBeCloseTo(b.w, 6)
  expect(a.h).toBeCloseTo(b.h, 6)
}

describe('normalizeDeg', () => {
  it('收敛到 0/90/180/270（含负数与超过一圈）', () => {
    expect(normalizeDeg(0)).toBe(0)
    expect(normalizeDeg(90)).toBe(90)
    expect(normalizeDeg(-90)).toBe(270)
    expect(normalizeDeg(450)).toBe(90)
    expect(normalizeDeg(-450)).toBe(270)
    expect(normalizeDeg(360)).toBe(0)
  })

  it('非 90 倍数按最近的 90 取整（pdf.js 会对非整角抛错）', () => {
    expect(normalizeDeg(91)).toBe(90)
    expect(normalizeDeg(134)).toBe(90)
    expect(normalizeDeg(136)).toBe(180)
    expect(normalizeDeg(15)).toBe(0)
  })

  it('NaN / Infinity 退化成 0，不把脏值传给渲染', () => {
    expect(normalizeDeg(Number.NaN)).toBe(0)
    expect(normalizeDeg(Number.POSITIVE_INFINITY)).toBe(0)
  })
})

describe('pageRotKey / parsePageRotKey', () => {
  it('往返一致', () => {
    const key = pageRotKey(3, 12)
    expect(key).toBe('3:12')
    expect(parsePageRotKey(key)).toEqual({ partIndex: 3, page: 12 })
  })

  it('非法键返回 null（草稿是外部可改的 JSON，不能信）', () => {
    expect(parsePageRotKey('')).toBeNull()
    expect(parsePageRotKey('7')).toBeNull()
    expect(parsePageRotKey('a:1')).toBeNull()
    expect(parsePageRotKey('1:0')).toBeNull() // 页号 1 起
    expect(parsePageRotKey('1:-2')).toBeNull()
  })
})

describe('rotateRefs', () => {
  it('顺时针 90 叠加，四次回到 0 且删键', () => {
    let map: PageRotMap | undefined
    for (let i = 1; i <= 4; i += 1) {
      map = rotateRefs(map, [R(0, 5)], 90)
      expect(getPageRot(map, R(0, 5))).toBe(((90 * i) % 360) as 0 | 90 | 180 | 270)
    }
    expect(map).toEqual({})
  })

  it('逆时针 -90 等于 270', () => {
    const map = rotateRefs(undefined, [R(0, 1)], -90)
    expect(getPageRot(map, R(0, 1))).toBe(270)
  })

  it('只改传入的页，其它页原样保留（批量旋转不能误伤邻居）', () => {
    const before = setRefsRotation(undefined, [R(0, 1), R(0, 2)], 90)
    const after = rotateRefs(before, [R(0, 2)], 90)
    expect(getPageRot(after, R(0, 1))).toBe(90)
    expect(getPageRot(after, R(0, 2))).toBe(180)
  })

  it('不同素材的同一页号互不影响（键含 partIndex）', () => {
    const map = rotateRefs(undefined, [R(0, 3)], 90)
    expect(getPageRot(map, R(1, 3))).toBe(0)
    expect(countRotated(map)).toBe(1)
  })

  it('不修改入参（不可变，store.update 依赖这一点）', () => {
    const before = setRefsRotation(undefined, [R(0, 1)], 90)
    const snapshot = { ...before }
    rotateRefs(before, [R(0, 1)], 90)
    expect(before).toEqual(snapshot)
  })
})

describe('setRefsRotation / resetRefsRotation', () => {
  it('设为绝对角度而不是叠加（右键「180°」点两次仍是 180）', () => {
    const once = setRefsRotation(undefined, [R(0, 1)], 180)
    const twice = setRefsRotation(once, [R(0, 1)], 180)
    expect(getPageRot(once, R(0, 1))).toBe(180)
    expect(getPageRot(twice, R(0, 1))).toBe(180)
  })

  it('重置回正并删键', () => {
    const map = setRefsRotation(undefined, [R(0, 1), R(0, 2)], 270)
    const reset = resetRefsRotation(map, [R(0, 1)])
    expect(getPageRot(reset, R(0, 1))).toBe(0)
    expect(getPageRot(reset, R(0, 2))).toBe(270)
    expect(Object.keys(reset)).toEqual(['0:2'])
  })
})

describe('countRotated', () => {
  const map: PageRotMap = { '0:1': 90, '0:4': 180, '2:3': 270 }

  it('不带 refs 数全包', () => {
    expect(countRotated(map)).toBe(3)
    expect(countRotated(undefined)).toBe(0)
  })

  it('带 refs 只数选区（工具栏「已旋转」按选区口径）', () => {
    expect(countRotated(map, [R(0, 1), R(0, 2), R(0, 4)])).toBe(2)
    expect(countRotated(map, [R(1, 1)])).toBe(0)
  })
})

describe('rotateNormRect：归一化坐标跟着页转', () => {
  const rect = { x: 0.1, y: 0.2, w: 0.3, h: 0.4 }

  it('0° 原样返回', () => {
    expect(rotateNormRect(rect, 0)).toEqual(rect)
  })

  it('90° 顺时针：左上角变 (1-y-h, x)，宽高互换', () => {
    closeRect(rotateNormRect(rect, 90), { x: 1 - 0.2 - 0.4, y: 0.1, w: 0.4, h: 0.3 })
  })

  it('180°：中心对称', () => {
    closeRect(rotateNormRect(rect, 180), { x: 1 - 0.1 - 0.3, y: 1 - 0.2 - 0.4, w: 0.3, h: 0.4 })
  })

  it('270°：90° 的逆变换', () => {
    closeRect(rotateNormRect(rect, 270), { x: 0.2, y: 1 - 0.1 - 0.3, w: 0.4, h: 0.3 })
  })

  it('转四次回到原点（框不会越转越偏）', () => {
    let r = rect
    for (let i = 0; i < 4; i += 1) r = rotateNormRect(r, 90)
    closeRect(r, rect)
  })

  it('整页矩形在任何角度下都还是整页', () => {
    const full = { x: 0, y: 0, w: 1, h: 1 }
    for (const deg of [90, 180, 270] as const) {
      closeRect(rotateNormRect(full, deg), full)
    }
  })
})

describe('rotatedSizeOf', () => {
  it('90/270 宽高互换，0/180 不变', () => {
    expect(rotatedSizeOf(595, 842, 0)).toEqual({ width: 595, height: 842 })
    expect(rotatedSizeOf(595, 842, 180)).toEqual({ width: 595, height: 842 })
    expect(rotatedSizeOf(595, 842, 90)).toEqual({ width: 842, height: 595 })
    expect(rotatedSizeOf(595, 842, 270)).toEqual({ width: 842, height: 595 })
  })
})

describe('rotationsForRange：给后端的编码', () => {
  const map: PageRotMap = { '0:1': 90, '0:3': 180, '0:4': 270, '0:9': 90, '1:3': 90 }

  it('只含区间内的非 0 页，按页码升序，格式 页码:角度', () => {
    expect(rotationsForRange(map, 0, 1, 5)).toBe('1:90,3:180,4:270')
  })

  it('区间外与其它素材的页都不带（后端切的是这个 partIndex 的这个区间）', () => {
    expect(rotationsForRange(map, 0, 3, 4)).toBe('3:180,4:270')
    expect(rotationsForRange(map, 1, 1, 5)).toBe('3:90')
  })

  it('没旋转就返回空串（后端据此跳过旋转路径）', () => {
    expect(rotationsForRange(map, 2, 1, 10)).toBe('')
    expect(rotationsForRange(undefined, 0, 1, 10)).toBe('')
  })

  it('区间反着传也按从小到大处理（调用方偶发笔误不该静默丢旋转）', () => {
    expect(rotationsForRange(map, 0, 4, 3)).toBe('3:180,4:270')
  })
})

describe('rotatedRefsOf', () => {
  it('只列非 0 的页，且能把键解析回 partIndex/page', () => {
    const refs = rotatedRefsOf({ '0:2': 90, '1:7': 180 })
    expect(refs).toHaveLength(2)
    expect(refs).toContainEqual({ partIndex: 0, page: 2 })
    expect(refs).toContainEqual({ partIndex: 1, page: 7 })
  })

  it('忽略脏键与 0 值', () => {
    const map = { 'bad': 90, '0:0': 90, '0:5': 0 } as unknown as PageRotMap
    expect(rotatedRefsOf(map)).toEqual([])
  })
})
