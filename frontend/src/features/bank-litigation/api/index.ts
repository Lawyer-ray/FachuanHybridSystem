/**
 * 银行批量诉讼 · 场景 2 全流程 API 层（出口）。
 *
 * ═══ 这个 feature 为什么单独存在 ═══
 * 场景 2（一份合同 → 批量出案 → 起诉 → 立案 → 归档）在后端已经**全部打通**，
 * 但前端一直没有入口：`cases` / `oa-filing` / `court-filing` / `doc-convert`
 * 这些能力只散落在各 feature 里被零碎用到，没有一个页面把这条链路串起来。
 * 本 feature 就是那条链路的唯一入口。
 *
 * ═══ 端点来源（全部已与 OpenAPI 核对）═══
 *   案件与就绪度   /api/v1/cases/*
 *   LPR 计息       /api/v1/lpr/*
 *   要素式转换     /api/v1/doc-convert/*
 *   律所 OA        /api/v1/oa-filing/*、/api/v1/oa-stamp/*、/api/v1/oa-archive/*
 *   一张网立案     /api/v1/court-filing/*
 *   整包分段       /api/v1/pdf-splitting/*
 *
 * ═══ 为什么是一个目录而不是一个文件 ═══
 * 单文件曾到 394 行并承载 7 个后端业务域（cases / doc-convert / oa-filing /
 * court-filing / oa-stamp / oa-archive / pdf-splitting）+ 30 个请求函数。
 * 拆分点是「一个后端域一个文件」（与 material-prep 的 api/ 目录同一套做法），
 * 不是机械切行：拆分后本文件只做 barrel re-export，消费方继续
 * `from '../api'` 不变。
 *
 * ═══ 为什么按「域」拆成多个 client 而不是一个 ═══
 * 与 material-prep 的写法一致：每个 prefix 一个 client，路径只写后半段。
 * 好处是换前缀（比如 oa-filing 将来挪到 /oa/filing）只改一处。
 *
 * ⚠️ 不要改成只 re-export 一个子集：子模块之间有共享的客户端实例
 * （`casesApi` 被 `materials.ts` 复用），整组导出才是「7 个 prefix」这条约定。
 */

export * from './timeouts'
export * from './cases'
export * from './doc-convert'
export * from './oa'
export * from './court-filing'
export * from './pdf-splitting'
export * from './materials'
