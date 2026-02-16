/**
 * Reminders Feature Module
 * 重要日期提醒功能模块
 *
 * @module features/reminders
 */

// Types
export type {
  ReminderType,
  ReminderStatus,
  Reminder,
  ReminderInput,
  ReminderTypeOption,
  ReminderFilters,
} from './types'

export { REMINDER_TYPE_LABELS } from './types'

// Schemas
export { reminderFormSchema } from './schemas'
export type { ReminderFormData } from './schemas'

// Utils
export {
  getReminderStatus,
  getStatusStyles,
  getStatusStylesFromDueAt,
  filterReminders,
  STATUS_STYLES,
} from './utils'

// API
export { reminderApi } from './api'

// Hooks
export { useReminders, useReminder, useReminderTypes } from './hooks/use-reminders'
export { remindersQueryKey, reminderQueryKey, reminderTypesQueryKey } from './hooks/use-reminders'

// Hooks - Mutations
export { useReminderMutations } from './hooks/use-reminder-mutations'
export type { UseReminderMutationsReturn, UpdateReminderParams } from './hooks/use-reminder-mutations'

// Components
export { ReminderFilters } from './components/ReminderFilters'
export { ReminderForm } from './components/ReminderForm'
export type { ReminderFormProps } from './components/ReminderForm'
export { ReminderFormDialog } from './components/ReminderFormDialog'
export type { ReminderFormDialogProps } from './components/ReminderFormDialog'
export { DeleteConfirmDialog } from './components/DeleteConfirmDialog'
export type { DeleteConfirmDialogProps } from './components/DeleteConfirmDialog'
export { ReminderList } from './components/ReminderList'
export type { ReminderListProps } from './components/ReminderList'
