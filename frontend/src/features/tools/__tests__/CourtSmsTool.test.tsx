import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { CourtSmsTool } from '../components/CourtSmsTool'

vi.mock('lucide-react', () => ({
  Search: () => <svg data-testid="search" />,
  Plus: () => <svg data-testid="plus" />,
  Trash2: () => <svg data-testid="trash" />,
  Loader2: () => <svg data-testid="loader" />,
  LinkIcon: () => <svg data-testid="link" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/lib/date', () => ({ formatDate: (d: string) => d ?? '' }))

vi.mock('../hooks/use-court-sms', () => ({
  useCourtSmsList: () => ({ data: [], isLoading: false }),
}))

vi.mock('../api/court-sms', () => ({
  courtSmsApi: {
    deleteSms: vi.fn(),
    parseSms: vi.fn(),
    assignCase: vi.fn(),
  },
}))

vi.mock('@/features/cases/api', () => ({
  caseApi: { list: vi.fn().mockResolvedValue([]) },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/routes/paths', () => ({
  generatePath: { courtSmsDetail: (id: number) => `/admin/tools/court-sms/${id}` },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))
vi.mock('@/components/ui/checkbox', () => ({
  Checkbox: (props: Record<string, unknown>) => <input type="checkbox" {...props} />,
}))
vi.mock('@/components/ui/textarea', () => ({
  Textarea: (props: Record<string, unknown>) => <textarea {...props} />,
}))
vi.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: Record<string, unknown>) => <label {...props}>{children}</label>,
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children }: { children: React.ReactNode }) => <td>{children}</td>,
  TableHead: ({ children }: { children: React.ReactNode }) => <th>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}))
vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

describe('CourtSmsTool', () => {
  it('renders page title', () => {
    render(<MemoryRouter><CourtSmsTool /></MemoryRouter>)
    expect(screen.getByText('法院短信')).toBeInTheDocument()
  })




})
