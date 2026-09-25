/**
 * vitest 全局准备。
 * 目前用例以纯逻辑（domain/日期/归一化）为主，不依赖 React 渲染，
 * 因此这里不引入 @testing-library——保持零新增依赖。
 * 若将来需要组件测试，再加 jest-dom 与 testing-library。
 */
