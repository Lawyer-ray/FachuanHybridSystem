/**
 * vitest 全局准备（vite.config.ts 的 setupFiles）。
 *
 * 当前没有全局初始化要做：环境按文件切换（node 为默认，组件测试在文件头写
 * `// @vitest-environment jsdom` 并用 @testing-library/react），jsdom 清理由
 * testing-library 各用例自行负责。本文件保留为空壳，新增真正需要全局生效的
 * 桩（如 matchMedia / ResizeObserver 默认实现）时写在这里。
 */

/**
 * 收件箱档位偏好是**模块级**状态（"本次会话记住用户自己选过的档位"），
 * 同一个测试文件里跑多个用例时会从上一个用例漏到下一个——于是在某个用例里
 * 点过「一张网」之后，后面所有断言"默认是邮箱"的用例都会莫名其妙失败。
 * 统一在每个用例前清空，让每个用例都从"首次进入"的状态起步。
 */
import { beforeEach } from 'vitest'
import { resetInboxSourcePreference } from './features/material-prep/inbox/default-source'

beforeEach(() => {
  resetInboxSourcePreference()
})
