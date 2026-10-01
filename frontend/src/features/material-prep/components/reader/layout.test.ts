import { COL_GAP, COL_MIN_W, effectiveCols, fitPageWidth, maxColsAllowed, rowWidth } from './layout'

describe('maxColsAllowed', () => {
  it('容器越窄列数越少，最小为 1', () => {
    // n 列需要 n*COL_MIN_W + (n-1)*GAP 的宽度
    expect(maxColsAllowed(COL_MIN_W - 1)).toBe(1)
    expect(maxColsAllowed(COL_MIN_W)).toBe(1)
    expect(maxColsAllowed(2 * COL_MIN_W + COL_GAP - 1)).toBe(1)
    expect(maxColsAllowed(2 * COL_MIN_W + COL_GAP)).toBe(2)
    expect(maxColsAllowed(0)).toBe(1)
  })
})

describe('effectiveCols', () => {
  it('用户列数与容器上限取小，最小 1', () => {
    expect(effectiveCols(3, 10000)).toBe(3)
    expect(effectiveCols(3, 2 * COL_MIN_W + COL_GAP)).toBe(2)
    expect(effectiveCols(1, 0)).toBe(1)
  })
})

describe('fitPageWidth', () => {
  it('100% 缩放：均分宽度有 960 上限，floor 保证行宽不超画布', () => {
    const w = fitPageWidth(2000, 2, 1)
    expect(w).toBe(960) // min(960, (2000-18)/2=991) → 960
    const w2 = fitPageWidth(998, 2, 1)
    expect(w2).toBe(Math.floor((998 - COL_GAP) / 2)) // 490，非 round
    expect(rowWidth(w2, 2)).toBeLessThanOrEqual(998)
  })

  it('页宽下限 140；缩放倍率乘在页宽上、下限垫底', () => {
    expect(fitPageWidth(100, 1, 1)).toBe(140)
    expect(fitPageWidth(2000, 2, 1.5)).toBe(Math.floor(960 * 1.5))
    // 窄宽度 + 放大：fit*zoom 超过下限后按下限不再生效
    expect(fitPageWidth(100, 1, 2)).toBe(200)
  })

  it('单列不吃列间距', () => {
    expect(fitPageWidth(500, 1, 1)).toBe(500)
    expect(rowWidth(500, 1)).toBe(500)
  })
})

describe('rowWidth', () => {
  it('行宽 = 列数×页宽 + (列数-1)×间距', () => {
    expect(rowWidth(300, 3)).toBe(3 * 300 + 2 * COL_GAP)
  })
})
