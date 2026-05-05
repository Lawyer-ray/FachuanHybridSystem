import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { MaterialBindItem, MaterialCategory } from '../types'
import { caseQueryKey } from './use-case'

export function useMaterialMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidateCase = () => {
    queryClient.invalidateQueries({ queryKey: caseQueryKey(caseId) })
  }

  const uploadMaterials = useMutation({
    mutationFn: (files: File[]) => caseApi.uploadMaterials(caseId, files),
    onSuccess: invalidateCase,
  })

  const bindMaterials = useMutation({
    mutationFn: (items: MaterialBindItem[]) => caseApi.bindMaterials(caseId, items),
    onSuccess: invalidateCase,
  })

  const replaceMaterial = useMutation({
    mutationFn: ({ materialId, newAttachmentId }: { materialId: number | string; newAttachmentId: number }) =>
      caseApi.replaceMaterial(caseId, materialId, newAttachmentId),
    onSuccess: invalidateCase,
  })

  const renameGroup = useMutation({
    mutationFn: ({ typeId, newTypeName, updateGlobal }: { typeId: number; newTypeName: string; updateGlobal?: boolean }) =>
      caseApi.renameMaterialGroup(caseId, typeId, newTypeName, updateGlobal),
    onSuccess: invalidateCase,
  })

  const deleteMaterial = useMutation({
    mutationFn: (materialId: number | string) => caseApi.deleteMaterial(caseId, materialId),
    onSuccess: invalidateCase,
  })

  const deleteAllMaterials = useMutation({
    mutationFn: (category: MaterialCategory) => caseApi.deleteAllMaterials(caseId, category),
    onSuccess: invalidateCase,
  })

  const saveGroupOrder = useMutation({
    mutationFn: ({ category, orderedTypeIds, side, supervisingAuthorityId }: { category: string; orderedTypeIds: number[]; side?: string; supervisingAuthorityId?: number }) =>
      caseApi.saveMaterialGroupOrder(caseId, category, orderedTypeIds, side, supervisingAuthorityId),
    onSuccess: invalidateCase,
  })

  return { uploadMaterials, bindMaterials, replaceMaterial, renameGroup, deleteMaterial, deleteAllMaterials, saveGroupOrder }
}

export default useMaterialMutations
