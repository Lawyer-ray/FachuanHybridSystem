/**
 * 材料预处理 feature 的对外出口。
 * 其它 feature / app 层只应从这里引，不穿透内部目录。
 */

export { DeskPage } from './components/DeskPage'

/**
 * 全局重置材料预处理阅读器状态与 PDF/字节缓存（登出清理用，换账号不得残留
 * 上一账号的材料内容）。走动态 import：这条依赖链上有 pdfjs-dist（~1MB 懒加载
 * chunk），静态引会把整个材料预处理域拖进首屏包（AppNavbar 经 HomePage 进
 * entry chunk）——调用方（AppNavbar）应经本出口调用，不再穿透内部 store 路径。
 */
export function resetMaterialPrepState(): Promise<void> {
  return import('./store').then((m) => {
    m.useReader.getState().resetAll()
  })
}

/**
 * 后端收件箱消息（/inbox）的行类型。home 的收件箱卡消费同一端点，
 * 经此出口复用（Pick 投影见 features/home/api/inbox.ts），避免两份手抄漂移。
 */
export type { InboxMessage } from './types'
