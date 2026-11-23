/**
 * 办案主页的具名业务默认值（含一处交互阈值）。
 *
 * 「新建项目」建出来的空白合同/案件要带一组默认字段（案由留空、案型民事、
 * 首审阶段、固定收费），这些值在 api/project.ts 的请求体里必须逐字保持——
 * 后端按这些字段初始化 OA 立案口径。散在请求体里当字面量时，改口径要全文搜
 * `'civil'` / `5000`，还会有第二份副本（本域已出现过一份 5000 的模板副本，
 * 见 templates.ts 的 createFromTemplate）。
 */

import type { WorkbenchFilter } from './types'

/** 空白项目的默认案型（后端 case_type 枚举） */
export const DEFAULT_CASE_TYPE = 'civil'

/** 空白项目初始案件的阶段（后端 current_stage 枚举） */
export const DEFAULT_CASE_STAGE = 'first_trial'

/** 空白项目的默认律师费（元）：建完由律师在详情页改，建时不填会显示「--」 */
export const DEFAULT_FIXED_FEE_AMOUNT = 5000

/**
 * 列表默认筛选（在办 + 全部类目/收费方式 + 空搜索）。
 *
 * 三处同口径：页面初始筛选、FilterBar「清除全部筛选」、空态判定「有没有在筛」。
 * 此前三处各写一份字面量，任何一处改默认值（比如默认也看已归档）就会与另两处分叉。
 */
export const DEFAULT_FILTER: WorkbenchFilter = { status: 'active', cat: '', fee: '', q: '' }

/**
 * 阶段行点击的「单击折叠 / 双击改名」区分延时（ms）。
 *
 * 阶段名既是单击折叠区又是双击改名目标，只能靠延时区分。取系统双击间隔的常见值：
 * 短于它不显迟钝，长了才点得开改名。
 */
export const ROW_CLICK_DELAY_MS = 220
