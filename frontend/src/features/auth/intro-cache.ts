/**
 * 登录页开场动画的「已播放过」记忆（localStorage）。
 *
 * 播放策略：本机播过一次即写入标记，之后进入登录页直接跳过动画；
 * 用户清除浏览器缓存（localStorage 一并清空）则标记消失、恢复播放。
 * 与「减少动态效果」系统偏好的跳过（无障碍）相互独立、任一命中即跳。
 *
 * storage 可注入（单测用内存实现）；缺省绑定 localStorage，读失败按
 * 未播放过处理——宁可多播一次动画，不可因隐私模式等抛错卡住登录页。
 */
import { INTRO_PLAYED_KEY } from './constants'

type IntroStorage = Pick<Storage, 'getItem' | 'setItem'>

function resolveStorage(storage?: IntroStorage): IntroStorage | undefined {
  return storage ?? (typeof localStorage === 'undefined' ? undefined : localStorage)
}

export function hasPlayedIntro(storage?: IntroStorage): boolean {
  const s = resolveStorage(storage)
  if (!s) return false
  try {
    return s.getItem(INTRO_PLAYED_KEY) === '1'
  } catch {
    return false
  }
}

export function markIntroPlayed(storage?: IntroStorage): void {
  const s = resolveStorage(storage)
  if (!s) return
  try {
    s.setItem(INTRO_PLAYED_KEY, '1')
  } catch {
    // 写失败（隐私模式/配额满）不影响播放，仅下次可能再播
  }
}
