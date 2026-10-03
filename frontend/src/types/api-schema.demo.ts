/**
 * api-schema 生成物的示范消费 + 编译期冒烟（无业务逻辑）。
 *
 * openapi-typescript 生成物（api-schema.d.ts）的标准用法有两种索引方式：
 *   - 按 schema 名：components['schemas']['<SchemaName>']
 *   - 按 operationId：operations['<operationId>']['responses'][200]['content']['application/json']
 *
 * 本文件以文书识别的 search-cases 端点（court-sms 人工分配复用的同一端点）为例，
 * 两种方式各取一次响应行类型并互证一致——后端端点改名 / 返回结构变化并再生成
 * schema 后（再生成流程见本目录 README.md），`tsc -b` 会在这里最先报错，
 * 提醒消费方同步。各 feature 手写类型可按此方式渐进替换（不强制）。
 */
import type { components, operations } from './api-schema'

/** GET /api/v1/document-recognition/court-document/search-cases 的响应行（按 schema 名取） */
export type SearchCasesRow = components['schemas']['CaseSearchResultSchema']

/**
 * 同一响应行按 operationId 取。
 * NonNullable 剥掉 noUncheckedIndexedAccess 对数组元素补充的 undefined。
 */
export type SearchCasesRowByOp = NonNullable<
  operations['apps_document_recognition_api_document_recognition_api_search_cases_for_binding']['responses'][200]['content']['application/json'][number]
>

/** 两条取法形状一致时为 true，漂移时为 never（下行赋值随即编译失败） */
export type AssertSearchCasesRowsMatch = SearchCasesRowByOp extends SearchCasesRow
  ? SearchCasesRow extends SearchCasesRowByOp
    ? true
    : never
  : never

/** 编译期断言落地：schema 漂移时该常量赋值报错（无运行时语义，勿引用） */
export const SEARCH_CASES_ROWS_MATCH: AssertSearchCasesRowsMatch = true
