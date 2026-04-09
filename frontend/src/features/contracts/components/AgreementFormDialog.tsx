import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { useClientsSelect } from '../hooks/use-clients-select'
import { Badge } from '@/components/ui/badge'
import type { SupplementaryAgreement } from '../types'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  agreement?: SupplementaryAgreement
  contractId: number
  onSubmit: (data: { contract_id: number; name?: string; party_ids?: number[] }) => void
  submitting?: boolean
}

export function AgreementFormDialog({ open, onOpenChange, agreement, contractId, onSubmit, submitting }: Props) {
  const { data: clients = [] } = useClientsSelect()
  const [name, setName] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])

  useEffect(() => {
    if (agreement) {
      setName(agreement.name ?? '')
      setSelectedIds(agreement.parties.map(p => p.client))
    } else {
      setName(''); setSelectedIds([])
    }
  }, [agreement, open])

  const toggle = (id: number) => setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{agreement ? '编辑补充协议' : '新增补充协议'}</DialogTitle></DialogHeader>
        <form onSubmit={e => { e.preventDefault(); onSubmit({ contract_id: contractId, name: name || undefined, party_ids: selectedIds.length > 0 ? selectedIds : undefined }) }} className="space-y-4">
          <div className="space-y-2">
            <Label>协议名称</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="可选" />
          </div>
          <div className="space-y-2">
            <Label>关联当事人</Label>
            <div className="flex flex-wrap gap-2">
              {clients.map(c => (
                <Badge key={c.id} variant={selectedIds.includes(c.id) ? 'default' : 'outline'} className="cursor-pointer" onClick={() => toggle(c.id)}>
                  {c.name}
                </Badge>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
            <Button type="submit" disabled={submitting}>{submitting ? '提交中...' : '保存'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
