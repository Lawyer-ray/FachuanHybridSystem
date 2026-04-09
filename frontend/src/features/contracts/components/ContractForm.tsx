import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { PATHS } from '@/routes/paths'
import { useContractMutations } from '../hooks/use-contract-mutations'
import { useLawyers } from '../hooks/use-lawyers'
import { useClientsSelect } from '../hooks/use-clients-select'
import {
  CASE_TYPE_LABELS, FEE_MODE_LABELS, PARTY_ROLE_LABELS,
  type CaseType, type FeeMode, type PartyRole, type Contract, type ContractInput, type ContractUpdate,
} from '../types'

interface Props {
  mode: 'create' | 'edit'
  contract?: Contract
}

export function ContractForm({ mode, contract }: Props) {
  const navigate = useNavigate()
  const { createContract, updateContract } = useContractMutations()
  const { data: lawyers = [] } = useLawyers()
  const { data: clients = [] } = useClientsSelect()

  const [name, setName] = useState(contract?.name ?? '')
  const [caseType, setCaseType] = useState<CaseType>(contract?.case_type ?? 'civil')
  const [feeMode, setFeeMode] = useState<FeeMode>((contract?.fee_mode as FeeMode) ?? 'FIXED')
  const [fixedAmount, setFixedAmount] = useState(contract?.fixed_amount?.toString() ?? '')
  const [riskRate, setRiskRate] = useState(contract?.risk_rate?.toString() ?? '')
  const [customTerms, setCustomTerms] = useState(contract?.custom_terms ?? '')
  const [specifiedDate, setSpecifiedDate] = useState(contract?.specified_date ?? '')
  const [startDate, setStartDate] = useState(contract?.start_date ?? '')
  const [endDate, setEndDate] = useState(contract?.end_date ?? '')
  const [selectedLawyers, setSelectedLawyers] = useState<number[]>(
    contract?.assignments.map(a => a.lawyer_id) ?? []
  )
  const [parties, setParties] = useState<{ client_id: number; role: PartyRole }[]>(
    contract?.contract_parties.map(p => ({ client_id: p.client, role: p.role })) ?? []
  )
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) { toast.error('请输入合同名称'); return }
    if (selectedLawyers.length === 0) { toast.error('请至少指派一个律师'); return }

    setSubmitting(true)
    try {
      if (mode === 'create') {
        const data: ContractInput = {
          name, case_type: caseType, fee_mode: feeMode,
          fixed_amount: fixedAmount ? Number(fixedAmount) : null,
          risk_rate: riskRate ? Number(riskRate) : null,
          custom_terms: customTerms || null,
          specified_date: specifiedDate || null,
          start_date: startDate || null,
          end_date: endDate || null,
          lawyer_ids: selectedLawyers,
          parties: parties.length > 0 ? parties : undefined,
        }
        await createContract.mutateAsync(data)
        toast.success('合同创建成功')
        navigate(PATHS.ADMIN_CONTRACTS)
      } else if (contract) {
        const data: ContractUpdate = {
          name, case_type: caseType, fee_mode: feeMode,
          fixed_amount: fixedAmount ? Number(fixedAmount) : null,
          risk_rate: riskRate ? Number(riskRate) : null,
          custom_terms: customTerms || null,
          specified_date: specifiedDate || null,
          start_date: startDate || null,
          end_date: endDate || null,
          parties: parties.length > 0 ? parties : undefined,
        }
        await updateContract.mutateAsync({ id: contract.id, data })
        toast.success('合同更新成功')
        navigate(PATHS.ADMIN_CONTRACTS)
      }
    } catch { toast.error('操作失败') } finally { setSubmitting(false) }
  }

  const toggleLawyer = (id: number) => {
    setSelectedLawyers(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const addParty = () => setParties(prev => [...prev, { client_id: 0, role: 'PRINCIPAL' }])
  const removeParty = (idx: number) => setParties(prev => prev.filter((_, i) => i !== idx))
  const updateParty = (idx: number, field: 'client_id' | 'role', val: number | string) => {
    setParties(prev => prev.map((p, i) => i === idx ? { ...p, [field]: field === 'client_id' ? Number(val) : val } : p))
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Card>
        <CardHeader><CardTitle>基本信息</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>合同名称 *</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="输入合同名称" />
          </div>
          <div className="space-y-2">
            <Label>案件类型</Label>
            <Select value={caseType} onValueChange={v => setCaseType(v as CaseType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(CASE_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>指定日期</Label>
            <Input type="date" value={specifiedDate} onChange={e => setSpecifiedDate(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>开始日期</Label>
            <Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>结束日期</Label>
            <Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>收费信息</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>收费模式</Label>
            <Select value={feeMode} onValueChange={v => setFeeMode(v as FeeMode)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(FEE_MODE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {(feeMode === 'FIXED' || feeMode === 'SEMI_RISK') && (
            <div className="space-y-2">
              <Label>{feeMode === 'FIXED' ? '固定金额' : '前期金额'}</Label>
              <Input type="number" value={fixedAmount} onChange={e => setFixedAmount(e.target.value)} placeholder="0.00" />
            </div>
          )}
          {(feeMode === 'SEMI_RISK' || feeMode === 'FULL_RISK') && (
            <div className="space-y-2">
              <Label>风险比例(%)</Label>
              <Input type="number" value={riskRate} onChange={e => setRiskRate(e.target.value)} placeholder="0" />
            </div>
          )}
          {feeMode === 'CUSTOM' && (
            <div className="space-y-2 sm:col-span-2">
              <Label>自定义条款</Label>
              <Input value={customTerms} onChange={e => setCustomTerms(e.target.value)} placeholder="输入自定义收费条款" />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>律师指派 *</CardTitle></CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {lawyers.map(l => (
              <Badge
                key={l.id}
                variant={selectedLawyers.includes(l.id) ? 'default' : 'outline'}
                className="cursor-pointer"
                onClick={() => toggleLawyer(l.id)}
              >
                {l.real_name || l.username}
                {selectedLawyers[0] === l.id && ' (主办)'}
              </Badge>
            ))}
          </div>
          {lawyers.length === 0 && <p className="text-muted-foreground text-sm">暂无律师数据</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>当事人</CardTitle>
          <Button type="button" variant="outline" size="sm" onClick={addParty}>添加</Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {parties.map((p, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <Select value={String(p.client_id || '')} onValueChange={v => updateParty(idx, 'client_id', v)}>
                <SelectTrigger className="flex-1"><SelectValue placeholder="选择当事人" /></SelectTrigger>
                <SelectContent>
                  {clients.map(c => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={p.role} onValueChange={v => updateParty(idx, 'role', v)}>
                <SelectTrigger className="w-[120px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(PARTY_ROLE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
                </SelectContent>
              </Select>
              <Button type="button" variant="ghost" size="sm" onClick={() => removeParty(idx)}>×</Button>
            </div>
          ))}
          {parties.length === 0 && <p className="text-muted-foreground text-sm">未添加当事人</p>}
        </CardContent>
      </Card>

      <div className="flex gap-3">
        <Button type="submit" disabled={submitting}>{submitting ? '提交中...' : mode === 'create' ? '创建合同' : '保存修改'}</Button>
        <Button type="button" variant="outline" onClick={() => navigate(PATHS.ADMIN_CONTRACTS)}>取消</Button>
      </div>
    </form>
  )
}
