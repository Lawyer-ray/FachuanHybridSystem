import { createCrudMutations } from '@/lib/create-crud-mutations'
import { templateApi } from '../api'
import type { Template } from '../types'

export const useTemplateMutations = createCrudMutations<Template, unknown, unknown>({
  api: templateApi,
  listKey: ['templates'],
  detailKey: (id) => ['template', id],
})
