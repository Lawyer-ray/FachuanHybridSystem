"""
案件 Admin 简化测试

只测试最基本的功能，用于验证测试框架是否正常工作
"""
from .base_admin_test import BaseAdminTest


class TestCaseAdminSimple(BaseAdminTest):
    """案件 Admin 简化测试"""
    
    async def test_list_page_access(self):
        """测试列表页访问"""
        print(f"\n  测试: 列表页访问")
        
        await self.navigate_to_model('cases', 'case')
        
        # 保存页面结构用于调试
        await self.debug_page_structure('case_list_page.html')
        await self.take_screenshot('case_list_page')
        
        # 检查页面是否加载
        content = await self.page.content()
        
        # 检查是否包含 Django Admin 的标准元素
        has_content = '#content' in content or 'changelist' in content
        self.assert_true(has_content, "页面没有加载 Admin 内容")
        
        print(f"    ✅ 列表页访问成功")
    
    async def test_add_page_access(self):
        """测试添加页面访问"""
        print(f"\n  测试: 添加页面访问")
        
        await self.navigate_to_model('cases', 'case')
        await self.click_add_button()
        
        # 保存页面结构用于调试
        await self.debug_page_structure('case_add_page.html')
        await self.take_screenshot('case_add_page')
        
        # 检查页面是否加载
        content = await self.page.content()
        has_form = 'form' in content.lower()
        self.assert_true(has_form, "页面没有表单")
        
        print(f"    ✅ 添加页面访问成功")
        print(f"    ℹ️  页面结构已保存到 debug/case_add_page.html")
    
    async def test_edit_page_access(self):
        """测试编辑页面访问"""
        print(f"\n  测试: 编辑页面访问")
        
        await self.navigate_to_model('cases', 'case')
        
        # 检查是否有记录
        row_count = await self.get_table_row_count()
        if row_count == 0:
            print(f"    ⚠️  没有案件记录，跳过编辑页面测试")
            return
        
        # 点击第一条记录
        await self.click_first_edit_link()
        
        # 保存页面结构用于调试
        await self.debug_page_structure('case_edit_page.html')
        await self.take_screenshot('case_edit_page')
        
        # 检查页面是否加载
        content = await self.page.content()
        has_form = 'form' in content.lower()
        self.assert_true(has_form, "页面没有表单")
        
        print(f"    ✅ 编辑页面访问成功")
        print(f"    ℹ️  页面结构已保存到 debug/case_edit_page.html")
