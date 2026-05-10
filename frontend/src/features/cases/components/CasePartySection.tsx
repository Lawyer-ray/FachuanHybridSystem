import { useState } from 'react'
import { Link } from 'react-router'
import { X, Loader2, Search } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

import { generatePath } from '@/routes/paths'
import { usePartyMutations } from '../hooks/use-party-mutations'
import { useClientsSelect } from '@/features/contracts/hooks/use-clients-select'
import { LEGAL_STATUS_LABELS } from '../types'
import type { CaseParty } from '../types'

export interface CasePartySectionProps {
  parties: CaseParty[]
  editable?: boolean
  caseId?: number
}

export function CasePartySection({ parties, editable, caseId }: CasePartySectionProps) {
  const [open, setOpen] = useState(false)
  const [legalStatus, setLegalStatus] = useState('')
  const { data: clients } = useClientsSelect()
  const mutations = usePartyMutations(caseId ?? 0)

  const existingIds = new Set(parties.map(p => p.client))

  const handleSelect = (clientId: number) => {
    if (!caseId) return
    mutations.createParty.mutate(
      { case_id: caseId, client_id: clientId, legal_status: legalStatus || undefined },
      {
        onSuccess: () => { toast.success('已添加'); setOpen(false) },
        onError: (e) => toast.error(e.message || '添加失败'),
      },
    )
  }

  const handleDelete = (id: number) => {
    mutations.deleteParty.mutate(id, {
      onSuccess: () => toast.success('已删除'),
      onError: (e) => toast.error(e.message || '删除失败'),
    })
  }

  const filteredClients = (clients ?? []).filter(c => !existingIds.has(c.id))

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {parties.length === 0 && !editable && (
          <span className="text-muted-foreground text-xs">暂无当事人</span>
        )}
        {parties.map((party) => {
          const name = party.client_detail?.name ?? '未知'
          const statusLabel = party.legal_status
            ? (LEGAL_STATUS_LABELS[party.legal_status as keyof typeof LEGAL_STATUS_LABELS]?.zh ?? party.legal_status)
            : null
          return (
            <Badge key={party.id} variant="secondary" className="gap-1 pr-1 font-normal">
              <Link to={generatePath.clientDetail(party.client)} className="hover:underline">
                {name}
              </Link>
              {statusLabel && <span className="text-muted-foreground">({statusLabel})</span>}
              {editable && caseId && (
                <button
                  type="button"
                  onClick={() => handleDelete(party.id)}
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
              <div className="border-b px-3 py-2">
                <div className="text-xs text-muted-foreground mb-1.5">诉讼地位（可选）</div>
                <Select value={legalStatus} onValueChange={setLegalStatus}>
                  <SelectTrigger className="h-7 text-xs"><SelectValue placeholder="选择诉讼地位" /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(LEGAL_STATUS_LABELS).map(([v, l]) => (
                      <SelectItem key={v} value={v}>{l.zh}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Command>
                <CommandInput placeholder="搜索客户名称..." className="h-8 text-xs" />
                <CommandList className="max-h-[200px]">
                  <CommandEmpty>未找到匹配客户</CommandEmpty>
                  <CommandGroup>
                    {filteredClients.map((c) => (
                      <CommandItem
                        key={c.id}
                        value={c.name}
                        onSelect={() => handleSelect(c.id)}
                        className="text-xs cursor-pointer"
                      >
                        <Search className="size-3 mr-1.5 text-muted-foreground" />
                        <span className="flex-1">{c.name}</span>
                        <span className="text-muted-foreground text-[10px]">{c.client_type_label}</span>
                        {c.is_our_client && <Badge variant="outline" className="ml-1 text-[10px] px-1 py-0">我方</Badge>}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        )}

        {mutations?.createParty.isPending && <Loader2 className="size-3 animate-spin text-muted-foreground" />}
      </div>
    </div>
  )
}

export default CasePartySection
