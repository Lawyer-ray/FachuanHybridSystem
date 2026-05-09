import { createCrudMutations } from '@/lib/create-crud-mutations'
import { reminderApi } from '../api'
import type { Reminder, ReminderInput } from '../types'
import { reminderQueryKey } from './use-reminders'

export interface UpdateReminderParams {
  id: number
  data: ReminderInput
}

export type UseReminderMutationsReturn = ReturnType<typeof useReminderMutations>

const useBaseMutations = createCrudMutations<Reminder, ReminderInput, ReminderInput>({
  api: {
    create: (data) => reminderApi.create(data),
    update: (id, data) => reminderApi.update(id, data),
    delete: (id) => reminderApi.delete(id),
  },
  listKey: ['reminders'],
  detailKey: (id) => reminderQueryKey(id),
})

export function useReminderMutations() {
  const { create, update, delete: del } = useBaseMutations()
  return {
    createMutation: create,
    updateMutation: update,
    deleteMutation: del,
  }
}

export default useReminderMutations
