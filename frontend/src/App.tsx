import { AppRouter } from './app/router'

/**
 * 应用入口：只剩路由装配。
 *
 * 具体内容按关注点分散在 src/app/：
 * - `paths.ts`   路径常量与实例路径构造函数（唯一权威，禁止别处手拼）
 * - `preload.ts` 页面 chunk 的 lazy 声明 + 悬停/空闲预取
 * - `router.tsx` 顶层路由表、RequireAuth、旧路径前转
 * - `shell/`     已登录壳层（导航栏常驻、copilot 面板与 ⌘K 检索的状态机）
 *
 * App 本身不再持有任何状态或 effect：它是 main.tsx 的装配出口，长期保持这个形状。
 */
export default function App() {
  return <AppRouter />
}
