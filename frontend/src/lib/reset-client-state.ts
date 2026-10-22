/**
 * 客户端全量状态重置 —— 「主动退出」与「会话过期被踢」两条路径共用。
 *
 * 为什么必须共用（2026-10 审查 I-P1-2）：此前 AppNavbar.handleLogout 会清
 * react-query 缓存、材料预处理阅读器、PDF 缓存、AI 助手转录，而 api.ts 在
 * 401 刷新失败时只 clearTokens() 就跳 /login。同一浏览器换人登录时，上一账号
 * 的材料草稿/阅读器恢复点（localStorage）会残留给下一个人。
 *
 * 依赖链注意：material-prep 与 pdf 的清理链上有 pdfjs-dist（~1MB 懒加载
 * chunk），必须走动态 import，否则静态引会把整个材料预处理域拖进首屏包。
 * 本模块只被登出/过期路径调用，本身不引入静态重依赖。
 */
import { clearTokens } from '@/lib/token'

/** 清 react-query 缓存：否则换账号后在 staleTime 窗口内直接命中上一账号数据 */
export type QueryCacheCleaner = () => void

/**
 * 重置全部客户端状态（内存 + localStorage 命名空间）。
 *
 * @param clearQueryCache 由持有 QueryClient 的调用方注入（lib 层拿不到实例）
 */
export async function resetAllClientState(clearQueryCache?: QueryCacheCleaner): Promise<void> {
  clearTokens()
  clearQueryCache?.()

  // 动态 import：这三条链都带大依赖（pdfjs ~1MB），不能进首屏
  await Promise.all([
    import('@/features/material-prep')
      .then((m) => m.resetMaterialPrepState())
      .catch(() => {}),
    import('@/features/copilot')
      .then((m) => m.resetCopilotState())
      .catch(() => {}),
    import('@/lib/pdf')
      .then((m) => m.clearPdfCache())
      .catch(() => {}),
  ]).catch(() => {})
}
