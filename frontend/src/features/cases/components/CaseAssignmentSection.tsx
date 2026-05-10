import { useState } from 'react'
import { X, Loader2, Search, Phone } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

import { useAssignmentMutations } from '../hooks/use-assignment-mutations'
import { useLawyers } from '@/features/organization/hooks/use-lawyers'
import { useDebounce } from '@/hooks/use-debounce'
import type { CaseAssignment } from '../types'

export interface CaseAssignmentSectionProps {
  assignments: CaseAssignment[]
  editable?: boolean
  caseId?: number
}

export function CaseAssignmentSection({ assignments, editable, caseId }: CaseAssignmentSectionProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)
  const { data: lawyers, isLoading: lawyersLoading } = useLawyers({ search: debouncedSearch })
  const mutations = useAssignmentMutations(caseId ?? 0)

  const existingIds = new Set(assignments.map(a => a.lawyer))

  const handleSelect = (lawyerId: number) => {
    if (!caseId) return
    mutations.createAssignment.mutate(
      { case_id: caseId, lawyer_id: lawyerId },
      {
        onSuccess: () => { toast.success('已添加'); setOpen(false); setSearch('') },
        onError: (e) => toast.error(e.message || '添加失败'),
      },
    )
  }

  const handleDelete = (id: number) => {
    mutations.deleteAssignment.mutate(id, {
      onSuccess: () => toast.success('已删除'),
      onError: (e) => toast.error(e.message || '删除失败'),
    })
  }

  const filteredLawyers = (lawyers ?? []).filter(l => !existingIds.has(l.id))

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {assignments.length === 0 && !editable && (
          <span className="text-muted-foreground text-xs">暂无指派律师</span>
        )}
        {assignments.map((a) => {
          const name = a.lawyer_detail?.real_name || a.lawyer_detail?.username || '未知律师'
          const phone = a.lawyer_detail?.phone
          return (
            <Badge key={a.id} variant="secondary" className="gap-1 pr-1 font-normal">
              <span>{name}</span>
              {phone && (
                <span className="text-muted-foreground flex items-center gap-0.5 text-[10px]">
                  <Phone className="size-2.5" />{phone}
                </span>
              )}
              {editable && caseId && (
                <button
                  type="button"
                  onClick={() => handleDelete(a.id)}
                  className="ml-0.5 rounded-full p-0.5 hover:bg-destructive/20 hover:text-destructive transition-colors"
                >
                  <X className="size-3" />
                </button>
              )}
            </Badge>
          )
        })}

        {editable && caseId && (
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
              <Button variant="outline" size="xs" className="h-6 px-1.5 text-[11px]">
                + 添加
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[300px] p-0" align="start">
              <Command shouldFilter={false}>
                <CommandInput
                  placeholder="搜索律师姓名/手机号..."
                  className="h-8 text-xs"
                  value={search}
                  onValueChange={setSearch}
                />
                <CommandList className="max-h-[200px]">
                  {lawyersLoading && !lawyers && (
                    <div className="flex items-center justify-center py-4">
                      <Loader2 className="size-4 animate-spin text-muted-foreground" />
                    </div>
                  )}
                  <CommandEmpty>
                    {debouncedSearch ? '未找到匹配律师' : '输入关键词搜索律师'}
                  </CommandEmpty>
                  <CommandGroup>
                    {filteredLawyers.map((l) => (
                      <CommandItem
                        key={l.id}
                        value={String(l.id)}
                        onSelect={() => handleSelect(l.id)}
                        className="text-xs cursor-pointer"
                      >
                        <Search className="size-3 mr-1.5 text-muted-foreground" />
                        <span className="flex-1">{l.real_name || l.username}</span>
                        {l.phone && (
                          <span className="text-muted-foreground text-[10px] flex items-center gap-0.5">
                            <Phone className="size-2.5" />{l.phone}
                          </span>
                        )}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        )}

        {mutations?.createAssignment.isPending && <Loader2 className="size-3 animate-spin text-muted-foreground" />}
      </div>
    </div>
  )
}

export default CaseAssignmentSection
