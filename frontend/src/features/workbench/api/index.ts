/**
 * 办案主页 feature 的后端对接出口。
 *
 * 按资源拆为 contract / folder / invoice / stages 四个子模块，本文件只做 barrel
 * re-export，消费方继续 `from '../api'` / `from '../../api'` 不变
 * （api/client.ts 是被各子模块共用的客户端实例，不经 barrel 导出——它不是公开契约）。
 *
 * 2026-10 拆分缘起：单文件 api.ts 到 368 行越过 frontend/CLAUDE.md 的 350 行
 * 软红线，且合同 / 文件夹 / 发票三组资源混在一个文件里。拆分点是「资源边界」，
 * 不是机械切行；「另存为」链路（registerFolderSaveAsIntent + folderFileUrl）
 * 整组落在 ./folder，行为与拆分前逐字一致。
 *
 * 注意：**不要**把这里改成 `export * from './x'` 的聚合入口后再让
 * `*.dom.test.tsx` 去 mock './folder'——那些测试 mock 的是 `../../api`
 * （本文件），由 vitest 对 src 文件的默认 mock 隔离接住；一旦指针下沉，
 * 同一测试里 `vimock('../../api/client')` 才能生效，mock 边界会被迫跟着改。
 */

export * from './contract'
export * from './folder'
export * from './invoice'
export * from './stages'
