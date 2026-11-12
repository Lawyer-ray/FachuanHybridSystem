/**
 * 非诉线 · 演示数据的公共类型（**仅用于录屏演示**，不参与真实业务）
 *
 * 只放跨场景共用的类型：目前唯一一个是 `DemoDeliverable`，
 * 它同时被 NL1 的阶段表（`DEMO_NONLIT_PHASES`）与阶段抽屉组件使用。
 * 各场景自有类型留在各自模块，避免这里长成第二个「什么都往里塞」的桶。
 */

/** 阶段交付物（挂在阶段下的小文件） */
export interface DemoDeliverable {
  name: string
  pages: number
  status: 'done' | 'drafting' | 'pending'
  updatedAt: string
  owner: string
}
