import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface Column {
  key: string
  header: string
  placeholder?: string
  type?: 'text' | 'number'
}

interface InlineCrudTableProps {
  columns: Column[]
  rows: Record<string, string>[]
  onChange: (rows: Record<string, string>[]) => void
  addLabel?: string
}

export function InlineCrudTable({
  columns,
  rows,
  onChange,
  addLabel = '添加',
}: InlineCrudTableProps) {
  const [flashRow, setFlashRow] = useState<number | null>(null)

  const handleAdd = () => {
    // Check if last row has empty fields
    if (rows.length > 0) {
      const lastRow = rows[rows.length - 1]
      const hasEmpty = columns.some((col) => !lastRow[col.key]?.trim())
      if (hasEmpty) {
        setFlashRow(rows.length - 1)
        setTimeout(() => setFlashRow(null), 600)
        return
      }
    }
    const newRow: Record<string, string> = {}
    columns.forEach((col) => (newRow[col.key] = ''))
    onChange([...rows, newRow])
  }

  const handleDelete = (index: number) => {
    onChange(rows.filter((_, i) => i !== index))
  }

  const handleCellChange = (index: number, key: string, value: string) => {
    const updated = rows.map((row, i) =>
      i === index ? { ...row, [key]: value } : row
    )
    onChange(updated)
  }

  return (
    <div className="space-y-2">
      <div className="border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              {columns.map((col) => (
                <TableHead key={col.key}>{col.header}</TableHead>
              ))}
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={columns.length + 1}
                  className="h-16 text-center text-muted-foreground text-sm"
                >
                  暂无数据，点击下方按钮添加
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row, rowIndex) => (
                <TableRow
                  key={rowIndex}
                  className={flashRow === rowIndex ? 'animate-pulse bg-status-red-bg' : ''}
                >
                  {columns.map((col) => (
                    <TableCell key={col.key}>
                      <Input
                        value={row[col.key] ?? ''}
                        onChange={(e) =>
                          handleCellChange(rowIndex, col.key, e.target.value)
                        }
                        placeholder={col.placeholder}
                        type={col.type ?? 'text'}
                        className="h-8 text-sm"
                      />
                    </TableCell>
                  ))}
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-status-red hover:text-status-red"
                      onClick={() => handleDelete(rowIndex)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      <Button variant="outline" size="sm" onClick={handleAdd}>
        <Plus className="w-4 h-4 mr-1" />
        {addLabel}
      </Button>
    </div>
  )
}
