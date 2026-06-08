import {
  menuConfig,
  bottomMenuItems,
  isMenuGroup,
  getAllMenuPaths,
  findGroupByPath,
} from '../menu-config'

describe('menu-config', () => {
  describe('menuConfig', () => {
    it('is a non-empty array', () => {
      expect(Array.isArray(menuConfig)).toBe(true)
      expect(menuConfig.length).toBeGreaterThan(0)
    })

    it('contains dashboard as a top-level item', () => {
      const dashboard = menuConfig.find((item) => item.id === 'dashboard')
      expect(dashboard).toBeDefined()
      expect(dashboard!.label).toBe('仪表盘')
    })

    it('contains workbench as a top-level item', () => {
      const workbench = menuConfig.find((item) => item.id === 'workbench')
      expect(workbench).toBeDefined()
      expect(workbench!.label).toBe('工作台')
    })

    it('contains business group with clients, contracts, cases', () => {
      const business = menuConfig.find(
        (item) => isMenuGroup(item) && item.id === 'business',
      )
      expect(business).toBeDefined()
      if (isMenuGroup(business!)) {
        const ids = business!.items.map((i) => i.id)
        expect(ids).toContain('clients')
        expect(ids).toContain('contracts')
        expect(ids).toContain('cases')
      }
    })

    it('contains tools group with expected items', () => {
      const tools = menuConfig.find(
        (item) => isMenuGroup(item) && item.id === 'tools',
      )
      expect(tools).toBeDefined()
      if (isMenuGroup(tools!)) {
        const ids = tools!.items.map((i) => i.id)
        expect(ids).toContain('court-sms')
        expect(ids).toContain('courier-tracking')
        expect(ids).toContain('element-convert')
        expect(ids).toContain('lpr-calculator')
        expect(ids).toContain('content-ops')
      }
    })

    it('each item has required fields', () => {
      menuConfig.forEach((item) => {
        expect(item.id).toBeTruthy()
        expect(item.label).toBeTruthy()
        if (isMenuGroup(item)) {
          expect(Array.isArray(item.items)).toBe(true)
          item.items.forEach((subItem) => {
            expect(subItem.id).toBeTruthy()
            expect(subItem.label).toBeTruthy()
            expect(subItem.path).toBeTruthy()
            expect(subItem.icon).toBeDefined()
          })
        } else {
          expect(item.path).toBeTruthy()
          expect(item.icon).toBeDefined()
        }
      })
    })
  })

  describe('bottomMenuItems', () => {
    it('is a non-empty array', () => {
      expect(Array.isArray(bottomMenuItems)).toBe(true)
      expect(bottomMenuItems.length).toBeGreaterThan(0)
    })

    it('contains settings item', () => {
      const settings = bottomMenuItems.find((item) => item.id === 'settings')
      expect(settings).toBeDefined()
      expect(settings!.label).toBe('系统设置')
    })

    it('each item has required fields', () => {
      bottomMenuItems.forEach((item) => {
        expect(item.id).toBeTruthy()
        expect(item.label).toBeTruthy()
        expect(item.path).toBeTruthy()
        expect(item.icon).toBeDefined()
      })
    })
  })

  describe('isMenuGroup', () => {
    it('returns true for a group item', () => {
      const group = menuConfig.find((item) => 'items' in item)
      expect(group).toBeDefined()
      expect(isMenuGroup(group!)).toBe(true)
    })

    it('returns false for a top-level item', () => {
      const topLevel = menuConfig.find((item) => !('items' in item))
      expect(topLevel).toBeDefined()
      expect(isMenuGroup(topLevel!)).toBe(false)
    })
  })

  describe('getAllMenuPaths', () => {
    it('returns a non-empty array of paths', () => {
      const paths = getAllMenuPaths()
      expect(Array.isArray(paths)).toBe(true)
      expect(paths.length).toBeGreaterThan(0)
    })

    it('includes dashboard path', () => {
      const paths = getAllMenuPaths()
      expect(paths).toContain('/admin/dashboard')
    })

    it('includes workbench path', () => {
      const paths = getAllMenuPaths()
      expect(paths).toContain('/admin/workbench')
    })

    it('includes group item paths', () => {
      const paths = getAllMenuPaths()
      expect(paths).toContain('/admin/clients')
      expect(paths).toContain('/admin/cases')
      expect(paths).toContain('/admin/contracts')
    })

    it('includes bottom menu paths', () => {
      const paths = getAllMenuPaths()
      expect(paths).toContain('/admin/settings')
    })

    it('includes tool paths', () => {
      const paths = getAllMenuPaths()
      expect(paths).toContain('/admin/tools/court-sms')
      expect(paths).toContain('/admin/tools/lpr-calculator')
    })
  })

  describe('findGroupByPath', () => {
    it('returns business group for clients path', () => {
      expect(findGroupByPath('/admin/clients')).toBe('business')
    })

    it('returns business group for cases path', () => {
      expect(findGroupByPath('/admin/cases')).toBe('business')
    })

    it('returns tools group for court-sms path', () => {
      expect(findGroupByPath('/admin/tools/court-sms')).toBe('tools')
    })

    it('returns null for top-level item path', () => {
      expect(findGroupByPath('/admin/dashboard')).toBeNull()
    })

    it('returns null for unknown path', () => {
      expect(findGroupByPath('/admin/unknown')).toBeNull()
    })

    it('returns null for settings path', () => {
      expect(findGroupByPath('/admin/settings')).toBeNull()
    })
  })
})
