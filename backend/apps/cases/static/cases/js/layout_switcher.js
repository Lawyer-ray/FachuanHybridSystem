/**
 * 案件编辑页面折叠布局组件
 *
 * 功能：
 * 1. 将所有 fieldset 和 inline-group 转换为可折叠区块
 * 2. 折叠状态持久化到 localStorage
 * 3. 页面加载时自动恢复折叠状态
 */
(function() {
    'use strict';

    const COLLAPSED_KEY = 'case_admin_collapsed';

    // 从 localStorage 恢复折叠状态
    function getCollapsedStates() {
        try {
            const saved = localStorage.getItem(COLLAPSED_KEY);
            return saved ? JSON.parse(saved) : {};
        } catch (e) {
            return {};
        }
    }

    // 保存折叠状态到 localStorage
    function saveCollapsedStates(states) {
        try {
            localStorage.setItem(COLLAPSED_KEY, JSON.stringify(states));
        } catch (e) {
            console.warn('[折叠布局] 保存状态失败:', e);
        }
    }

    // 切换折叠状态
    function toggleCollapse(wrapper, sectionId, collapsedStates) {
        const content = wrapper.querySelector('.collapsible-content');
        const icon = wrapper.querySelector('.collapse-icon');
        const isCollapsed = wrapper.classList.contains('collapsed');

        if (isCollapsed) {
            wrapper.classList.remove('collapsed');
            if (content) content.style.display = '';
            collapsedStates[sectionId] = false;
        } else {
            wrapper.classList.add('collapsed');
            if (content) content.style.display = 'none';
            collapsedStates[sectionId] = true;
        }

        saveCollapsedStates(collapsedStates);
    }

    // 将元素转换为可折叠区块
    function makeCollapsible(element, title, sectionId, collapsedStates, defaultCollapsed = false) {
        // 检查是否已经处理过
        if (element.classList.contains('collapsible-processed')) {
            return;
        }
        element.classList.add('collapsible-processed');

        // 创建包装器
        const wrapper = document.createElement('div');
        wrapper.className = 'collapsible-wrapper';
        wrapper.setAttribute('data-section-id', sectionId);

        // 创建头部
        const header = document.createElement('div');
        header.className = 'collapsible-header';
        header.innerHTML = `
            <span class="collapse-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
            </span>
            <span class="collapsible-title">${title}</span>
        `;

        // 创建内容容器
        const content = document.createElement('div');
        content.className = 'collapsible-content';

        // 插入包装器
        element.parentNode.insertBefore(wrapper, element);
        wrapper.appendChild(header);
        content.appendChild(element);
        wrapper.appendChild(content);

        // 隐藏原有标题
        const h2 = element.querySelector('h2');
        if (h2) {
            h2.style.display = 'none';
        }

        // 恢复折叠状态
        const isCollapsed = collapsedStates[sectionId] !== undefined
            ? collapsedStates[sectionId]
            : defaultCollapsed;

        if (isCollapsed) {
            wrapper.classList.add('collapsed');
            content.style.display = 'none';
        }

        // 绑定点击事件
        header.addEventListener('click', () => {
            toggleCollapse(wrapper, sectionId, collapsedStates);
        });
    }

    // 初始化折叠布局
    function initCollapsibleLayout() {
        console.log('[折叠布局] 初始化...');

        const collapsedStates = getCollapsedStates();

        // 隐藏 Tab 导航（如果存在）
        const tabNav = document.querySelector('.fieldset-tabs-nav');
        if (tabNav) {
            tabNav.style.display = 'none';
        }

        // 处理主要 fieldsets
        const fieldsets = document.querySelectorAll('fieldset.module');
        fieldsets.forEach((fieldset, index) => {
            // 跳过 inline 内部的 fieldset，避免与 inline-group 折叠逻辑重复包装
            if (fieldset.closest('.inline-related') || fieldset.closest('.inline-group')) {
                return;
            }

            // 获取标题
            const h2 = fieldset.querySelector('h2');
            let title = h2 ? h2.textContent.trim() : `区块 ${index + 1}`;

            // 根据 class 确定 ID
            let sectionId = fieldset.id || '';
            if (fieldset.classList.contains('case-basic-info')) {
                sectionId = 'case-basic-info';
                title = title || '基本信息';
            } else if (fieldset.classList.contains('case-details')) {
                sectionId = 'case-details';
                title = title || '案件详情';
            } else if (fieldset.classList.contains('case-templates')) {
                sectionId = 'case-templates';
                title = title || '文件夹模板';
            } else if (!sectionId) {
                sectionId = `fieldset-${index}`;
            }

            // 显示 fieldset（可能被 Tab 布局隐藏）
            fieldset.style.display = '';
            fieldset.classList.remove('tab-active');

            // 默认折叠模板区块
            const defaultCollapsed = fieldset.classList.contains('case-templates');

            makeCollapsible(fieldset, title, sectionId, collapsedStates, defaultCollapsed);
        });

        // 处理 inline-group（案件当事人、主管机关、案件案号等）
        const inlineGroups = document.querySelectorAll('.inline-group');
        inlineGroups.forEach((group, index) => {
            const groupId = group.id || '';

            // 案件案号使用独立分组字段布局，不接入折叠包装，避免样式错位
            if (groupId.includes('case_numbers')) {
                return;
            }

            // 获取标题
            const h2 = group.querySelector('h2');
            let title = h2 ? h2.textContent.trim() : '';

            // 从 ID 推断标题
            if (!title) {
                if (groupId.includes('parties')) {
                    title = '案件当事人';
                } else if (groupId.includes('supervising')) {
                    title = '主管机关';
                } else if (groupId.includes('case_numbers')) {
                    title = '案件案号';
                } else if (groupId.includes('logs')) {
                    title = '案件日志';
                } else if (groupId.includes('chats')) {
                    title = '案件聊天';
                } else {
                    title = `关联数据 ${index + 1}`;
                }
            }

            const sectionId = groupId || `inline-group-${index}`;

            makeCollapsible(group, title, sectionId, collapsedStates, false);
        });

        console.log('[折叠布局] 初始化完成');
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCollapsibleLayout);
    } else {
        // DOM 已经加载完成，延迟执行确保其他脚本先运行
        setTimeout(initCollapsibleLayout, 100);
    }
})();
