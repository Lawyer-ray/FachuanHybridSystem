import React, { useCallback } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'

interface Column<T> {
  key: string
  header: string
  width?: string
  render?: (row: T) => React.ReactNode
}

interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  rowKey: (row: T) => string | number
  selectedKeys?: Set<string | number>
  onSelectChange?: (keys: Set<string | number>) => void
  onRowClick?: (row: T) => void
  emptyText?: string
  className?: string
}

function DataTableInner<T>({
  columns,
  data,
  rowKey,
  selectedKeys,
  onSelectChange,
  onRowClick,
  emptyText = '暂无数据',
  className,
}: DataTableProps<T>) {
  const hasSelection = !!onSelectChange

  const handleSelectAll = useCallback((checked: boolean) => {
    if (!onSelectChange) return
    if (checked) {
      onSelectChange(new Set(data.map(rowKey)))
    } else {
      onSelectChange(new Set())
    }
  }, [onSelectChange, data, rowKey])

  const handleSelectRow = useCallback((key: string | number, checked: boolean) => {
    if (!onSelectChange || !selectedKeys) return
    const next = new Set(selectedKeys)
    if (checked) next.add(key)
    else next.delete(key)
    onSelectChange(next)
  }, [onSelectChange, selectedKeys])

  const allSelected = data.length > 0 && selectedKeys?.size === data.length

  return (
    <div className={cn('border rounded-lg overflow-hidden', className)}>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              {hasSelection && (
                <TableHead className="w-10">
                  <Checkbox
                    checked={allSelected}
                    onCheckedChange={handleSelectAll}
                  />
                </TableHead>
              )}
              {columns.map((col) => (
                <TableHead
                  key={col.key}
                  style={col.width ? { width: col.width } : undefined}
                >
                  {col.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={columns.length + (hasSelection ? 1 : 0)}
                  className="h-24 text-center text-muted-foreground"
                >
                  {emptyText}
                </TableCell>
              </TableRow>
            ) : (
              data.map((row) => {
                const key = rowKey(row)
                return (
                  <TableRow
                    key={key}
                    className={cn(
                      onRowClick && 'cursor-pointer',
                      selectedKeys?.has(key) && 'bg-muted/30'
                    )}
                    onClick={() => onRowClick?.(row)}
                  >
                    {hasSelection && (
                      <TableCell>
                        <Checkbox
                          checked={selectedKeys?.has(key)}
                          onCheckedChange={(checked) =>
                            handleSelectRow(key, !!checked)
                          }
                          onClick={(e) => e.stopPropagation()}
                        />
                      </TableCell>
                    )}
                    {columns.map((col) => (
                      <TableCell key={col.key}>
                        {col.render
                          ? col.render(row)
                          : (row as Record<string, unknown>)[col.key]?.toString() ?? '-'}
                      </TableCell>
                    ))}
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

export const DataTable = React.memo(DataTableInner) as typeof DataTableInner
