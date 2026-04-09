/**
 * ClientTable - 当事人列表表格组件
 */

import { useNavigate } from 'react-router'
import { Users, User, Building2, Landmark, Copy } from 'lucide-react'
import { toast } from 'sonner'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { generatePath } from '@/routes/paths'
import { type Client, type ClientType } from '../types'
import { formatClientText } from '../utils/format-client-text'

export interface ClientTableProps {
  clients: Client[]
  isLoading?: boolean
}

function TableSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <TableRow key={i}>
          {[24, 40, 28].map((w, j) => (
            <TableCell key={j}><div className={`bg-muted h-4 w-${w} animate-pulse rounded`} /></TableCell>
          ))}
        </TableRow>
      ))}
    </>
  )
}

function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={5} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <Users className="text-muted-foreground size-6" />
          </div>
          <div className="text-center">
            <p className="text-muted-foreground text-sm font-medium">暂无当事人数据</p>
            <p className="text-muted-foreground/70 mt-1 text-xs">点击「新建当事人」按钮添加第一个当事人</p>
          </div>
        </div>
      </TableCell>
    </TableRow>
  )
}

const TYPE_CONFIG: Record<ClientType, { icon: typeof User; color: string; label: string }> = {
  natural: { icon: User, color: 'text-blue-600 dark:text-blue-400', label: '自然人' },
  legal: { icon: Building2, color: 'text-amber-600 dark:text-amber-400', label: '法人' },
  non_legal_org: { icon: Landmark, color: 'text-purple-600 dark:text-purple-400', label: '非法人组织' },
}

function formatIdNumber(idNumber: string | null): string {
  if (!idNumber) return '-'
  if (idNumber.length <= 8) return idNumber
  return `${idNumber.slice(0, 4)}****${idNumber.slice(-4)}`
}

function formatPhone(phone: string | null): string {
  if (!phone) return '-'
  if (phone.length !== 11) return phone
  return `${phone.slice(0, 3)}****${phone.slice(-4)}`
}

export function ClientTable({ clients, isLoading = false }: ClientTableProps) {
  const navigate = useNavigate()

  const handleRowClick = (client: Client) => {
    navigate(generatePath.clientDetail(client.id))
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="min-w-[540px]">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[60px] text-xs sm:text-sm">ID</TableHead>
            <TableHead className="w-[180px] text-xs sm:w-[220px] sm:text-sm">名称</TableHead>
            <TableHead className="w-[140px] text-xs sm:w-[180px] sm:text-sm">证件号码</TableHead>
            <TableHead className="w-[110px] text-xs sm:w-[140px] sm:text-sm">联系方式</TableHead>
            <TableHead className="w-[60px] text-xs sm:text-sm"><span className="sr-only">操作</span></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <TableSkeleton />
          ) : clients.length === 0 ? (
            <EmptyState />
          ) : (
            clients.map((client) => {
              const cfg = TYPE_CONFIG[client.client_type] || TYPE_CONFIG.natural
              const Icon = cfg.icon
              return (
                <TableRow
                  key={client.id}
                  onClick={() => handleRowClick(client)}
                  className="h-11 cursor-pointer hover:bg-muted/50 transition-colors sm:h-auto"
                >
                  <TableCell className="text-muted-foreground text-xs sm:text-sm">{client.id}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Icon className={`size-4 shrink-0 ${cfg.color}`} />
                      <span className="text-xs font-medium sm:text-sm">{client.name}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs sm:text-sm">
                    {formatIdNumber(client.id_number)}
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs sm:text-sm">
                    {formatPhone(client.phone)}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      onClick={(e) => {
                        e.stopPropagation()
                        navigator.clipboard.writeText(formatClientText(client))
                        toast.success('已复制当事人信息')
                      }}
                    >
                      <Copy className="size-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })
          )}
        </TableBody>
      </Table>
    </div>
  )
}
