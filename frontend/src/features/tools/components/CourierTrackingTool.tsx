import { Search, Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { useExpressTasks } from '../hooks/use-express-tasks'
import { formatDate } from '@/lib/date'

const CARRIER_LABELS: Record<string, string> = {
  sf: '顺丰速运',
  ems: 'EMS',
  unknown: '未知',
}

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  ocr_parsing: 'OCR识别中',
  waiting_login: '等待登录',
  querying: '查询中',
  success: '成功',
  failed: '失败',
}

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  success: 'default',
  querying: 'secondary',
  pending: 'outline',
  failed: 'destructive',
}

export function CourierTrackingTool() {
  const { data: tasks, isLoading } = useExpressTasks()

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">快递查询</h1>
          <p className="text-muted-foreground text-sm mt-1">查询法律文书快递状态</p>
        </div>
        <Button size="sm" onClick={() => {/* TODO: 打开添加快递对话框 */}}>
          <Plus className="mr-1.5 size-4" />添加快递
        </Button>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
          <Input type="text" placeholder="输入快递单号..." className="pl-9" />
        </div>
        <Button variant="outline">查询</Button>
      </div>

      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[60px]">ID</TableHead>
              <TableHead>任务名称</TableHead>
              <TableHead className="w-[100px]">承运商</TableHead>
              <TableHead>运单号</TableHead>
              <TableHead className="w-[80px]">状态</TableHead>
              <TableHead className="w-[160px]">创建时间</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 6 }).map((_, j) => (
                    <TableCell key={j}><div className="bg-muted h-4 w-20 animate-pulse rounded" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : (tasks ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-32 text-center text-muted-foreground">
                  暂无查询任务
                </TableCell>
              </TableRow>
            ) : (
              (tasks ?? []).map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="text-muted-foreground text-sm">{item.id}</TableCell>
                  <TableCell className="text-sm">{item.title || '-'}</TableCell>
                  <TableCell className="text-sm">{CARRIER_LABELS[item.carrier_type] ?? item.carrier_type}</TableCell>
                  <TableCell>
                    <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{item.tracking_number || '-'}</code>
                  </TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANT[item.status] ?? 'outline'} className="text-xs">
                      {STATUS_LABELS[item.status] ?? item.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">{formatDate(item.created_at)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
