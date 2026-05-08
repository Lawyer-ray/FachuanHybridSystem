export interface TrendItem {
  month: string
  count: number
  amount: string
}

export interface CaseTypeDistItem {
  type: string
  label: string
  count: number
}

export interface UpcomingReminderItem {
  id: number
  title: string
  due_at: string
  type_label: string
  is_overdue: boolean
}

export interface DashboardStats {
  client_count: number
  contract_count: number
  case_count: number
  monthly_fee: string
  case_trend: TrendItem[]
  contract_trend: TrendItem[]
  fee_trend: TrendItem[]
  case_type_distribution: CaseTypeDistItem[]
  case_status_distribution: Record<string, number>
  upcoming_reminders: UpcomingReminderItem[]
  overdue_count: number
  today_count: number
}
