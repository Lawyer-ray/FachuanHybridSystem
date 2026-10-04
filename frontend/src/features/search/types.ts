/** 全局检索单条命中（跨类别统一形状） */
export interface Hit {
  category: string
  id: number
  title: string
  subtitle: string
}

/** 类别 key 联合：CATEGORIES 是封闭字典，用联合类型索引（而非 Record<string, …>），
 *  让 noUncheckedIndexedAccess 下也不需要运行时判空 */
export type CategoryKey = 'cases' | 'clients' | 'contracts' | 'inbox' | 'court_sms' | 'contacts'
