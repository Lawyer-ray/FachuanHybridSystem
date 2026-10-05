// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { INTRO_PLAYED_KEY } from './constants'
import { hasPlayedIntro, markIntroPlayed } from './intro-cache'

describe('intro-cache 开场动画记忆', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('未播放过：首次访问（无缓存）返回 false', () => {
    expect(hasPlayedIntro()).toBe(false)
  })

  it('播放过：markIntroPlayed 后返回 true（有缓存即跳过动画）', () => {
    markIntroPlayed()
    expect(hasPlayedIntro()).toBe(true)
    expect(localStorage.getItem(INTRO_PLAYED_KEY)).toBe('1')
  })

  it('清除缓存：localStorage 清空后恢复为未播放（动画重新展示）', () => {
    markIntroPlayed()
    localStorage.clear() // 用户清浏览器缓存
    expect(hasPlayedIntro()).toBe(false)
  })

  it('存储读抛错按未播放处理（隐私模式不卡登录页）', () => {
    const throwing: Pick<Storage, 'getItem' | 'setItem'> = {
      getItem: () => {
        throw new DOMException('denied')
      },
      setItem: () => {
        throw new DOMException('denied')
      },
    }
    expect(hasPlayedIntro(throwing)).toBe(false)
    expect(() => markIntroPlayed(throwing)).not.toThrow()
  })
})
