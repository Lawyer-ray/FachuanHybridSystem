import type { components } from '@/types/api-schema'

/** 全局检索单条命中（跨类别统一形状；其余字段直接来自生成物 SearchResultItem） */
export type Hit = components['schemas']['SearchResultItem'] & {
  category: string
  /** 仅 projects 类有：contract=项目（委托合同）本身命中；case=挂在项目下的案件命中 */
  kind?: 'contract' | 'case'
}

/** 类别 key 联合：CATEGORIES 是封闭字典，用联合类型索引（而非 Record<string, …>），
 *  让 noUncheckedIndexedAccess 下也不需要运行时判空 */
export type CategoryKey = 'projects' | 'clients' | 'inbox' | 'court_sms' | 'contacts'
