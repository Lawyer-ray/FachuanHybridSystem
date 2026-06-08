import { getReminderStatus, getStatusStyles, getStatusStylesFromDueAt, filterReminders, STATUS_STYLES } from '../utils'

describe('reminders/utils', () => {
  describe('getReminderStatus', () => {
    it('returns normal for null dueAt', () => {
      expect(getReminderStatus(null)).toBe('normal')
    })

    it('returns overdue for past date', () => {
      expect(getReminderStatus('2020-01-01T00:00:00Z')).toBe('overdue')
    })

    it('returns upcoming for date within 7 days', () => {
      const future = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString()
      expect(getReminderStatus(future)).toBe('upcoming')
    })

    it('returns normal for date beyond 7 days', () => {
      const future = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString()
      expect(getReminderStatus(future)).toBe('normal')
    })

    it('returns upcoming for today', () => {
      const today = new Date()
      today.setHours(12, 0, 0, 0)
      expect(getReminderStatus(today.toISOString())).toBe('upcoming')
    })
  })

  describe('STATUS_STYLES', () => {
    it('has styles for all statuses', () => {
      expect(STATUS_STYLES.overdue).toBeTruthy()
      expect(STATUS_STYLES.upcoming).toBeTruthy()
      expect(STATUS_STYLES.normal).toBe('')
    })

    it('overdue style contains red', () => {
      expect(STATUS_STYLES.overdue).toContain('red')
    })

    it('upcoming style contains amber', () => {
      expect(STATUS_STYLES.upcoming).toContain('amber')
    })
  })

  describe('getStatusStyles', () => {
    it('returns overdue styles', () => {
      expect(getStatusStyles('overdue')).toBe(STATUS_STYLES.overdue)
    })

    it('returns upcoming styles', () => {
      expect(getStatusStyles('upcoming')).toBe(STATUS_STYLES.upcoming)
    })

    it('returns empty for normal', () => {
      expect(getStatusStyles('normal')).toBe('')
    })
  })

  describe('getStatusStylesFromDueAt', () => {
    it('returns empty for null', () => {
      expect(getStatusStylesFromDueAt(null)).toBe('')
    })

    it('returns red styles for past date', () => {
      expect(getStatusStylesFromDueAt('2020-01-01T00:00:00Z')).toContain('red')
    })
  })

  describe('filterReminders', () => {
    const reminders = [
      { id: 1, reminder_type: 'hearing', due_at: '2026-06-10T09:00:00Z', content: 'Test 1' },
      { id: 2, reminder_type: 'evidence_deadline', due_at: '2026-07-01T09:00:00Z', content: 'Test 2' },
      { id: 3, reminder_type: 'hearing', due_at: null, content: 'Test 3' },
    ] as any[]

    it('returns all when no filters', () => {
      expect(filterReminders(reminders, {})).toHaveLength(3)
    })

    it('filters by reminder type', () => {
      expect(filterReminders(reminders, { reminderType: 'hearing' })).toHaveLength(2)
    })

    it('filters by date range', () => {
      const result = filterReminders(reminders, {
        dateFrom: new Date('2026-06-01'),
        dateTo: new Date('2026-06-30'),
      })
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe(1)
    })

    it('excludes reminders with null due_at when date filter is set', () => {
      const result = filterReminders(reminders, {
        dateFrom: new Date('2026-01-01'),
      })
      expect(result).toHaveLength(2)
      expect(result.find(r => r.id === 3)).toBeUndefined()
    })
  })
})
