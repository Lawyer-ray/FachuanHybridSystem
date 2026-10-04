import type { components } from '@/types/api-schema'

/** 全局检索单条命中（跨类别统一形状；id/title/subtitle 直接来自生成物 SearchResultItem） */
export type Hit = components['schemas']['SearchResultItem'] & {
  category: string
}

/** 类别 key 联合：CATEGORIES 是封闭字典，用联合类型索引（而非 Record<string, …>），
 *  让 noUncheckedIndexedAccess 下也不需要运行时判空 */
export type CategoryKey = 'cases' | 'clients' | 'contracts' | 'inbox' | 'court_sms' | 'contacts'
