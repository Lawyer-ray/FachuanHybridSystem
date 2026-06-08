import { render, screen } from '@testing-library/react'
import { CaseTemplateSection } from '../components/CaseTemplateSection'

vi.mock('lucide-react', () => ({
  FileText: () => <svg data-testid="file-text" />,
  Download: () => <svg data-testid="download" />,
  Link2: () => <svg data-testid="link2" />,
  Unlink: () => <svg data-testid="unlink" />,
  Loader2: () => <svg data-testid="loader" />,
  ChevronDown: () => <svg data-testid="chevron-down" />,
  ChevronRight: () => <svg data-testid="chevron-right" />,
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: () => ({ data: null, isLoading: false }),
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('../api', () => ({
  caseApi: {
    listTemplates: vi.fn().mockResolvedValue([]),
    bindTemplate: vi.fn(),
    unbindTemplate: vi.fn(),
  },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

describe('CaseTemplateSection', () => {
  it('renders empty state when no categories', () => {
    render(<CaseTemplateSection categories={[]} parties={[]} caseId={1} />)
    expect(screen.getByText('暂无绑定模板')).toBeInTheDocument()
  })



  it('renders template category', () => {
    const categories = [{
      category: '起诉状',
      templates: [{ id: 1, name: '民事起诉状模板' }],
    }]
    render(<CaseTemplateSection categories={categories as never} parties={[]} caseId={1} />)
    expect(screen.getByText('民事起诉状模板')).toBeInTheDocument()
  })

})
