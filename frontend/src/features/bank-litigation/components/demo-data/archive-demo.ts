/**
 * 演示数据 · B3. OA 归档
 *
 * 归档操作日志 / 归档类别对比 / 材料明细。
 * 真实功能上线时整个文件删除即可。
 */

export interface ArchiveLogRow {
  at: string
  /** 动作：生成文件夹 / 上传材料 / 删除多余文件 / 同步案件材料 */
  action: string
  /** 涉及的文件或目录 */
  target: string
  by: string
  ok: boolean
  /** 失败原因（成功时为「—」） */
  note: string
}

export const DEMO_ARCHIVE_LOG: ArchiveLogRow[] = [
  { at: '11-03 10:41', action: '生成文件夹', target: '结案归档/某某银行个贷不良批量诉讼', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:42', action: '上传材料', target: '案卷封面.pdf（1 页）', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:42', action: '上传材料', target: '结案归档登记表.pdf（2 页）', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:44', action: '上传材料', target: '民事起诉状（定稿）.pdf（4 页）', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:45', action: '上传材料', target: '（20XX）粤0106民初XXXX号 民事判决书.pdf（7 页）', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:46', action: '删除多余文件', target: '办案工作日记_草稿.pdf', by: '黄某某', ok: true, note: '草稿不入卷' },
  { at: '11-02 17:12', action: '同步案件材料', target: '案件材料 → 归档目录（9 份）', by: '房某某', ok: false, note: '有 1 份为低置信度分段，需先复核' },
  { at: '11-02 16:58', action: '上传材料', target: '办案服务质量监督卡.pdf（1 页）', by: '房某某', ok: true, note: '—' },
  { at: '11-01 15:20', action: '生成文件夹', target: '结案归档/某某银行信用卡批量诉讼', by: '黄某某', ok: false, note: '必需项缺 2 项，生成被拦' },
  { at: '11-01 09:34', action: '上传材料', target: '授权委托书（扫描件）.pdf（2 页）', by: '房某某', ok: true, note: '—' },
]

export interface ArchiveCategoryRow {
  /** 归档类别 */
  category: string
  /** 检查清单项数（执业规范口径） */
  items: number
  /** 其中必需项 */
  required: number
  /** 本所该类已归档卷数（近一年） */
  archived: number
  /** 该类特有材料（一句话，展示用） */
  only: string
}

export const DEMO_ARCHIVE_CATEGORIES: ArchiveCategoryRow[] = [
  { category: '诉讼', items: 20, required: 11, archived: 128, only: '判决书 / 庭审笔录 / 代理词' },
  { category: '非诉', items: 12, required: 7, archived: 64, only: '尽职调查报告 / 法律意见书' },
  { category: '刑事', items: 18, required: 10, archived: 23, only: '会见笔录 / 阅卷笔录 / 辩护词' },
]

export interface ArchiveMaterialMeta {
  /** 材料页数（多份合并时为总页数） */
  pages: number
  /** 上传或生成时间 */
  at: string
  /** 来源文件名（合同文件夹 / 案件材料里的原名） */
  source: string
}

export const DEMO_ARCHIVE_MATERIALS: Record<string, ArchiveMaterialMeta> = {
  lt_1: { pages: 1, at: '11-03 10:42', source: '案卷封面_模板_2026.docx' },
  lt_2: { pages: 2, at: '11-03 10:42', source: '结案归档登记表_模板_2026.docx' },
  lt_3: { pages: 3, at: '11-03 10:43', source: '案卷目录_生成.pdf' },
  lt_4: { pages: 12, at: '10-21 14:08', source: '委托代理合同_签署版.pdf' },
  lt_5: { pages: 2, at: '10-21 14:09', source: '律师费发票_扫描.pdf' },
  lt_6: { pages: 9, at: '11-02 17:35', source: '律师办案工作日记_汇总.pdf' },
  lt_7: { pages: 4, at: '10-30 15:12', source: '民事起诉状（定稿）.docx' },
  lt_8: { pages: 6, at: '10-28 10:22', source: '阅卷笔录_扫描.pdf' },
  lt_9: { pages: 5, at: '10-27 16:40', source: '会见笔录_谭某某.pdf' },
  lt_10: { pages: 18, at: '10-29 11:25', source: '调查材料_银行流水.pdf' },
  lt_11: { pages: 11, at: '10-25 09:18', source: '诉讼保全申请书及裁定书.pdf' },
  lt_12: { pages: 3, at: '11-02 11:05', source: '代理意见_一审.pdf' },
  lt_13: { pages: 2, at: '10-26 14:30', source: '集体讨论记录_2026Q3.pdf' },
  lt_14: { pages: 1, at: '10-22 09:44', source: '出庭通知书_扫描.pdf' },
  lt_15: { pages: 7, at: '11-01 16:40', source: '代理词_一审.pdf' },
  lt_16: { pages: 24, at: '11-01 16:42', source: '庭审笔录_扫描.pdf' },
  lt_17: { pages: 7, at: '11-03 10:45', source: '（20XX）粤0106民初XXXX号 民事判决书.pdf' },
  lt_18: { pages: 1, at: '11-02 16:58', source: '办案服务质量监督卡_模板.pdf' },
  lt_19: { pages: 2, at: '11-02 17:02', source: '办案小结_定稿.docx' },
  lt_20: { pages: 2, at: '11-01 09:34', source: '授权委托书（扫描件）.pdf' },
}
