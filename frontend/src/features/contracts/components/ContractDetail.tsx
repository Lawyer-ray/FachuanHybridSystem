import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'
import { Edit, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PATHS, generatePath } from '@/routes/paths'
import { useContract } from '../hooks/use-contract'
import { useContractMutations } from '../hooks/use-contract-mutations'
import { ContractInfoCard } from './ContractInfoCard'
import { PaymentList } from './PaymentList'
import { SupplementaryAgreementList } from './SupplementaryAgreementList'
import { FolderBindingManager } from './FolderBindingManager'

export function ContractDetail({ contractId }: { contractId: string }) {
  const navigate = useNavigate()
  const { data: contract, isLoading, error } = useContract(contractId)
  const { deleteContract } = useContractMutations()
  const [deleteOpen, setDeleteOpen] = useState(false)

  const handleDelete = useCallback(async () => {
    try {
      await deleteContract.mutateAsync(contractId)
      toast.success('合同已删除')
      navigate(PATHS.ADMIN_CONTRACTS)
    } catch { toast.error('删除失败') }
  }, [deleteContract, contractId, navigate])

  if (isLoading) return (
    <div className="space-y-6">
      <div className="bg-muted h-4 w-40 animate-pulse rounded" />
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="bg-muted h-6 w-64 animate-pulse rounded" />
        </div>
        <div className="flex gap-2">
          <div className="bg-muted h-9 w-20 animate-pulse rounded" />
          <div className="bg-muted h-9 w-20 animate-pulse rounded" />
        </div>
      </div>
      <div className="bg-muted h-10 w-full max-w-md animate-pulse rounded" />
      <div className="bg-muted h-64 w-full animate-pulse rounded-lg" />
    </div>
  )

  if (error || !contract) return (
    <div className="flex min-h-[300px] flex-col items-center justify-center">
      <p className="text-muted-foreground">合同不存在或无权访问</p>
      <Button variant="outline" className="mt-4" onClick={() => navigate(PATHS.ADMIN_CONTRACTS)}>返回列表</Button>
    </div>
  )

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="text-sm" aria-label="Breadcrumb">
        <ol className="flex items-center gap-1.5">
          <li>
            <span className="text-muted-foreground hover:text-foreground cursor-pointer transition-colors" onClick={() => navigate(PATHS.ADMIN_CONTRACTS)}>
              合同
            </span>
          </li>
          <li className="text-muted-foreground">/</li>
          <li className="text-foreground truncate max-w-[300px]">{contract.name}</li>
        </ol>
      </nav>

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold truncate min-w-0">{contract.name}</h1>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" size="sm" onClick={() => navigate(generatePath.contractEdit(contractId))} className="transition-colors">
            <Edit className="mr-1.5 size-4" />编辑
          </Button>
          <Button variant="outline" size="sm" className="text-destructive hover:text-destructive hover:bg-destructive/10 transition-colors" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="mr-1.5 size-4" />删除
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="info">
        <TabsList>
          <TabsTrigger value="info">基本信息</TabsTrigger>
          <TabsTrigger value="payments">收款记录 ({contract.payments.length})</TabsTrigger>
          <TabsTrigger value="agreements">补充协议 ({contract.supplementary_agreements.length})</TabsTrigger>
          <TabsTrigger value="folder">文件管理</TabsTrigger>
        </TabsList>
        <TabsContent value="info" className="mt-4">
          <ContractInfoCard contract={contract} />
        </TabsContent>
        <TabsContent value="payments" className="mt-4">
          <PaymentList contractId={contract.id} payments={contract.payments} />
        </TabsContent>
        <TabsContent value="agreements" className="mt-4">
          <SupplementaryAgreementList contractId={contract.id} agreements={contract.supplementary_agreements} />
        </TabsContent>
        <TabsContent value="folder" className="mt-4">
          <FolderBindingManager contractId={contract.id} />
        </TabsContent>
      </Tabs>

      {/* Delete Dialog */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>删除合同「{contract.name}」后无法恢复，关联的案件也会被删除。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground">删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
