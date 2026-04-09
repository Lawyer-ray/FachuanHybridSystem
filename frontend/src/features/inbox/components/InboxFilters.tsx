import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'

export interface InboxFiltersProps {
  search: string
  onSearchChange: (value: string) => void
  hasAttachments: string
  onHasAttachmentsChange: (value: string) => void
}

export function InboxFilters({
  search,
  onSearchChange,
  hasAttachments,
  onHasAttachmentsChange,
}: InboxFiltersProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="relative flex-1 sm:max-w-xs">
        <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
        <Input
          type="text"
          placeholder="搜索主题、发件人、正文..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9 pr-9"
        />
        {search && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onSearchChange('')}
            className="absolute right-1 top-1/2 size-7 -translate-y-1/2 p-0 hover:bg-transparent"
          >
            <X className="text-muted-foreground hover:text-foreground size-4" />
          </Button>
        )}
      </div>

      <Select value={hasAttachments} onValueChange={onHasAttachmentsChange}>
        <SelectTrigger className="w-full sm:w-[140px]">
          <SelectValue placeholder="全部消息" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部消息</SelectItem>
          <SelectItem value="true">有附件</SelectItem>
          <SelectItem value="false">无附件</SelectItem>
        </SelectContent>
      </Select>
    </div>
  )
}
