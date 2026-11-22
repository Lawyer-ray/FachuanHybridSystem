/**
 * vitest 全局准备（vite.config.ts 的 setupFiles）。
 *
 * 当前没有全局初始化要做：环境按文件切换（node 为默认，组件测试在文件头写
 * `// @vitest-environment jsdom` 并用 @testing-library/react），jsdom 清理由
 * testing-library 各用例自行负责。本文件保留为空壳，新增真正需要全局生效的
 * 桩（如 matchMedia / ResizeObserver 默认实现）时写在这里。
 */
