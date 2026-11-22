/**
 * bank-litigation · 域常量
 *
 * 放**规范级常量**（照搬后端、变更频率极低、猜错会导致业务缺项的东西）。
 * 演示态的假数据不放这里，放 `demo-data/`。
 */

/**
 * 归档清单项（与后端 ChecklistItem 同构，省略前端用不到的字段）
 */
export interface ArchiveItem {
  code: string
  name: string
  /** 是否必需项（缺了无法归档） */
  required: boolean
  /** 材料从哪来：模板生成 / 合同文件夹 / 案件材料 / 手工上传 */
  source: 'template' | 'contract' | 'case' | 'manual'
  /** 是否已就位 */
  done: boolean
  /** 已就位的文件名（展示用） */
  file?: string
}

/**
 * 诉讼类归档清单（20 项）。
 *
 * 顺序与名称严格对齐 `apps/contracts/services/archive/constants.py`
 * 的 `LITIGATION_CHECKLIST`。这份常量在前端留一份只读副本是**有代价的**
 * （后端改动要同步），但比让前端猜「有哪些项」要好：
 * 清单是执业规范，变更频率极低，而猜错会导致归档缺项。
 */
export const LITIGATION_CHECKLIST: Omit<ArchiveItem, 'done' | 'file'>[] = [
  { code: 'lt_1', name: '案卷封面', required: true, source: 'template' },
  { code: 'lt_2', name: '结案归档登记表', required: true, source: 'template' },
  { code: 'lt_3', name: '案卷目录', required: true, source: 'template' },
  { code: 'lt_4', name: '委托合同、风险告知书', required: true, source: 'contract' },
  { code: 'lt_5', name: '收费凭证', required: false, source: 'contract' },
  { code: 'lt_6', name: '律师办案工作日记', required: true, source: 'template' },
  { code: 'lt_7', name: '起诉书、上诉书或答辩书', required: true, source: 'case' },
  { code: 'lt_8', name: '阅卷笔录', required: false, source: 'case' },
  { code: 'lt_9', name: '会见当事人谈话笔录', required: false, source: 'case' },
  { code: 'lt_10', name: '调查材料等案件关联材料', required: false, source: 'case' },
  { code: 'lt_11', name: '诉讼保全申请书、证据保全申请书、先行给付申请书和法院裁定书', required: false, source: 'case' },
  { code: 'lt_12', name: '承办律师代理意见', required: false, source: 'case' },
  { code: 'lt_13', name: '集体讨论记录', required: false, source: 'case' },
  { code: 'lt_14', name: '出庭通知书', required: false, source: 'case' },
  { code: 'lt_15', name: '代理词', required: false, source: 'case' },
  { code: 'lt_16', name: '庭审笔录', required: false, source: 'case' },
  { code: 'lt_17', name: '判决书、裁定书、调解书、上诉书', required: true, source: 'case' },
  { code: 'lt_18', name: '办案服务质量监督卡', required: true, source: 'template' },
  { code: 'lt_19', name: '办案小结', required: true, source: 'template' },
  { code: 'lt_20', name: '授权委托证明材料', required: true, source: 'contract' },
]

/** 材料来源 → 展示名 */
export const SOURCE_LABEL: Record<ArchiveItem['source'], string> = {
  template: '模板生成',
  contract: '合同文件夹',
  case: '案件材料',
  manual: '手工上传',
}
