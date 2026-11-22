/**
 * 办案主页的具名业务默认值。
 *
 * 「新建项目」建出来的空白合同/案件要带一组默认字段（案由留空、案型民事、
 * 首审阶段、固定收费），这些值在 api/project.ts 的请求体里必须逐字保持——
 * 后端按这些字段初始化 OA 立案口径。散在请求体里当字面量时，改口径要全文搜
 * `'civil'` / `5000`，还会有第二份副本（本域已出现过一份 5000 的模板副本，
 * 见 templates.ts 的 createFromTemplate）。
 */

/** 空白项目的默认案型（后端 case_type 枚举） */
export const DEFAULT_CASE_TYPE = 'civil'

/** 空白项目初始案件的阶段（后端 current_stage 枚举） */
export const DEFAULT_CASE_STAGE = 'first_trial'

/** 空白项目的默认律师费（元）：建完由律师在详情页改，建时不填会显示「--」 */
export const DEFAULT_FIXED_FEE_AMOUNT = 5000
