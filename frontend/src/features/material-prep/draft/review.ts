/**
 * 复核清单的数据层：把分散在四个字段里的待复核信号归一成同一种 `ReviewItem[]`。
 *
 * ═══ 为什么必须归一 ═══
 * 律师打开材料包看到的是「第31页」「第23页」这些页卡，而「这页要复核什么」散在
 * `engineDisagreements`（双引擎分歧）、`pageQualityByMi` 里的 `doc_missing` / `graphic_pages` /
 * `sparse_pages`（识别质量，按源分槽）、`inconsistencies`（跨页不一致）、`seg.qualityFlags`
 * （段级标记）四处。UI 若是逐处各取各的，就会出现「页头徽标说 3 项、抽屉里只列出
 * 2 项」这种自相矛盾——律师只会认为这个功能不可信。所以先在这里合成一张表，
 * 页头徽标、抽屉、正文批注、页面框全部只读这一张表，数字天然一致。
 *
 * ═══ 拆成三块 ═══
 * - `review-ids.ts`：`ReviewItem` 形状与 `reviewItemId`——进草稿 JSON 的持久化契约；
 * - `review-items.ts`：四类信号源的提取与归一（`reviewItemsOf`）；
 * - `review-sort.ts`：展示用的全序与按页分组。
 *
 * 本文件只做出口，消费方与单测继续从 `./review` 引，import 路径不变。
 */
export { reviewItemId } from './review-ids'
export type { ReviewItem, ReviewItemKind } from './review-ids'
export { reviewItemsOf } from './review-items'
export { sortReviewItems, groupByPage } from './review-sort'
