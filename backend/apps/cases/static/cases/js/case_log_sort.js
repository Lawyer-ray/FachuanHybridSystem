/**
 * 案件日志排序功能
 */

(function() {
    'use strict';

    // 等待 DOM 加载完成
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCaseLogSort);
    } else {
        initCaseLogSort();
    }

    function initCaseLogSort() {
        const logsGroup = document.getElementById('logs-group');
        if (!logsGroup) return;

        const h2 = logsGroup.querySelector('h2');
        if (!h2) return;

        // 创建排序按钮
        const sortBtn = document.createElement('button');
        sortBtn.type = 'button';
        sortBtn.className = 'case-log-sort-btn';
        sortBtn.textContent = '倒序';
        sortBtn.dataset.order = 'desc'; // 默认倒序

        // 插入到标题后面
        h2.appendChild(sortBtn);

        // 初始化：默认倒序排列
        sortLogs('desc');

        // 点击排序按钮
        sortBtn.addEventListener('click', function() {
            const currentOrder = this.dataset.order;
            const newOrder = currentOrder === 'desc' ? 'asc' : 'desc';

            this.dataset.order = newOrder;
            this.textContent = newOrder === 'desc' ? '倒序' : '正序';

            sortLogs(newOrder);
        });
    }

    function sortLogs(order) {
        const logsGroup = document.getElementById('logs-group');
        if (!logsGroup) return;

        const itemsContainer = logsGroup.querySelector('.djn-items');
        if (!itemsContainer) return;

        // 获取所有日志条目（排除空表单和分隔符）
        const logItems = Array.from(itemsContainer.querySelectorAll('.djn-inline-form'))
            .filter(item => !item.classList.contains('djn-empty-form') && item.id !== 'logs-empty');

        if (logItems.length === 0) return;

        // 按照 ID 排序（logs-0, logs-1, logs-2...）
        logItems.sort((a, b) => {
            const aId = parseInt(a.id.replace('logs-', '')) || 0;
            const bId = parseInt(b.id.replace('logs-', '')) || 0;

            if (order === 'desc') {
                return bId - aId; // 倒序：最新的在前
            } else {
                return aId - bId; // 正序：最早的在前
            }
        });

        // 重新排列 DOM
        const emptyForm = itemsContainer.querySelector('.djn-empty-form');
        const separator = itemsContainer.querySelector('.djn-item.djn-no-drag');

        // 清空容器
        itemsContainer.innerHTML = '';

        // 添加分隔符（如果存在）
        if (separator) {
            itemsContainer.appendChild(separator);
        }

        // 按新顺序添加日志条目
        logItems.forEach(item => {
            itemsContainer.appendChild(item);
        });

        // 添加空表单（如果存在）
        if (emptyForm) {
            itemsContainer.appendChild(emptyForm);
        }
    }
})();
