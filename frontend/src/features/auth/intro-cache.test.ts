/**
 * intro-cache 测试（node 环境）。
 *
 * 播放策略的核心容错：读失败按「未播放」处理（宁可多播一次动画，
 * 不可因隐私模式抛错卡住登录页）；写失败不影响流程。
 */
import { describe, expect, it, vi } from 'vitest'

import { hasPlayedIntro, markIntroPlayed } from './intro-cache'
import { INTRO_PLAYED_KEY } from './constants'

function memoryStorage(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial))
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => {
      map.set(k, v)
    },
    _map: map,
  }
}

describe('hasPlayedIntro', () => {
  it('无标记时为 false', () => {
    expect(hasPlayedIntro(memoryStorage())).toBe(false)
  })

  it('标记为 1 时为 true', () => {
    expect(hasPlayedIntro(memoryStorage({ [INTRO_PLAYED_KEY]: '1' }))).toBe(true)
  })

  it('标记为其他值时为 false（只认 1）', () => {
    expect(hasPlayedIntro(memoryStorage({ [INTRO_PLAYED_KEY]: 'true' }))).toBe(false)
  })

  it('storage 读取抛错时降级为 false（宁可多播一次）', () => {
    const broken = {
      getItem: () => {
        throw new Error('SecurityError')
      },
      setItem: () => {},
    }
    expect(hasPlayedIntro(broken)).toBe(false)
  })
})

describe('markIntroPlayed', () => {
  it('写入标记后 hasPlayedIntro 为 true', () => {
    const s = memoryStorage()
    markIntroPlayed(s)
    expect(hasPlayedIntro(s)).toBe(true)
  })

  it('写入抛错时不抛出（隐私模式/配额满不影响播放）', () => {
    const broken = {
      getItem: () => null,
      setItem: () => {
        throw new Error('QuotaExceededError')
      },
    }
    expect(() => markIntroPlayed(broken)).not.toThrow()
  })

  it('写入的键与读取的键一致', () => {
    const setItem = vi.fn()
    markIntroPlayed({ getItem: () => null, setItem })
    expect(setItem).toHaveBeenCalledWith(INTRO_PLAYED_KEY, '1')
  })
})
