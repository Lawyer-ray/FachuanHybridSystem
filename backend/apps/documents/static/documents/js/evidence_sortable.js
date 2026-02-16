/**
 * 证据明细拖拽排序脚本
 *
 * 使用 SortableJS 实现证据明细的拖拽排序功能。
 *
 * Requirements: 4.2, 4.3
 */

(function() {
    'use strict';

    // 等待 DOM 加载完成
    document.addEventListener('DOMContentLoaded', function() {
        initEvidenceSortable();
        initEvidenceMergeProgress();
    });

    /**
     * 初始化证据明细排序
     */
    function initEvidenceSortable() {
        // 查找证据明细表格
        const inlineGroup = document.querySelector('.inline-group');
        if (!inlineGroup) return;

        const tbody = inlineGroup.querySelector('tbody');
        if (!tbody) return;

        // 检查是否是证据明细内联（通过 global_order_display 字段判断）
        const isEvidenceInline = inlineGroup.querySelector('.field-global_order_display') !== null;
        if (!isEvidenceInline) return;

        // 动态加载 SortableJS
        loadSortableJS(function() {
            initSortable(tbody);
        });
    }

    function initEvidenceMergeProgress() {
        const match = window.location.pathname.match(/\/admin\/documents\/evidencelist\/(\d+)\/change\//);
        if (!match) return;

        const listId = match[1];
        const container = ensureMergeProgressContainer();
        if (!container) return;

        let timer = null;

        function stop() {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
        }

        function scheduleNext() {
            stop();
            timer = setTimeout(poll, 1500);
        }

        function render(data) {
            const status = data.status;
            const progress = Number(data.progress || 0);
            const current = Number(data.current || 0);
            const total = Number(data.total || 0);
            const message = data.message || '';
            const error = data.error || '';

            const textEl = container.querySelector('[data-role="merge-text"]');
            const barEl = container.querySelector('[data-role="merge-bar"]');
            const errEl = container.querySelector('[data-role="merge-error"]');

            if (!textEl || !barEl || !errEl) return;

            container.style.display = status === 'processing' || status === 'failed' ? '' : 'none';
            barEl.style.width = `${Math.max(0, Math.min(100, progress))}%`;

            if (status === 'processing') {
                errEl.style.display = 'none';
                errEl.textContent = '';
                let detail = `${progress}% (${current}/${total})`;
                if (message) detail += ` ${message}`;
                textEl.textContent = `PDF 合并中：${detail}`;
            } else if (status === 'failed') {
                textEl.textContent = 'PDF 合并失败';
                errEl.style.display = '';
                errEl.textContent = error || '未知错误';
            }
        }

        function poll() {
            fetch(`/admin/documents/evidencelist/${listId}/merge-status/`, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(function(response) {
                if (!response.ok) throw new Error('请求失败');
                return response.json();
            })
            .then(function(data) {
                render(data);
                if (data.status === 'processing') {
                    scheduleNext();
                } else {
                    stop();
                }
            })
            .catch(function() {
                scheduleNext();
            });
        }

        poll();
    }

    function ensureMergeProgressContainer() {
        let container = document.getElementById('evidence-merge-progress');
        if (container) return container;

        const content = document.getElementById('content');
        if (!content) return null;

        container = document.createElement('div');
        container.id = 'evidence-merge-progress';
        container.className = 'evidence-merge-progress';
        container.innerHTML = `
            <div class="evidence-merge-progress__row">
                <div data-role="merge-text" class="evidence-merge-progress__text"></div>
                <div class="evidence-merge-progress__track" aria-hidden="true">
                    <div data-role="merge-bar" class="evidence-merge-progress__bar"></div>
                </div>
            </div>
            <div data-role="merge-error" class="evidence-merge-progress__error"></div>
        `;

        content.insertBefore(container, content.firstChild);
        return container;
    }

    /**
     * 动态加载 SortableJS
     */
    function loadSortableJS(callback) {
        // 检查是否已加载
        if (typeof Sortable !== 'undefined') {
            callback();
            return;
        }

        // 从 CDN 加载
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js';
        script.onload = callback;
        document.head.appendChild(script);
    }

    /**
     * 初始化 Sortable
     */
    function initSortable(tbody) {
        // 添加拖拽手柄样式
        addDragHandles(tbody);

        // 创建 Sortable 实例
        new Sortable(tbody, {
            handle: '.drag-handle',
            animation: 150,
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            dragClass: 'sortable-drag',
            onEnd: function(evt) {
                updateOrderNumbers(tbody);
                saveOrder(tbody);
            }
        });
    }

    /**
     * 添加拖拽手柄
     */
    function addDragHandles(tbody) {
        const rows = tbody.querySelectorAll('tr.form-row:not(.empty-form)');
        rows.forEach(function(row) {
            // 检查是否已有手柄
            if (row.querySelector('.drag-handle')) return;

            // 优先添加到 global_order_display 列，否则添加到第一个可见列
            const targetCell = row.querySelector('td.field-global_order_display') || row.querySelector('td:not([style*="display: none"])');
            if (targetCell) {
                const handle = document.createElement('span');
                handle.className = 'drag-handle';
                handle.innerHTML = '⋮⋮';
                handle.title = '拖拽排序';
                targetCell.insertBefore(handle, targetCell.firstChild);
            }
        });
    }

    /**
     * 更新序号
     */
    function updateOrderNumbers(tbody) {
        const rows = tbody.querySelectorAll('tr.form-row:not(.empty-form)');
        rows.forEach(function(row, index) {
            const orderInput = row.querySelector('input[name$="-order"]');
            if (orderInput) {
                orderInput.value = index + 1;
            }
        });
    }

    /**
     * 保存排序（通过 AJAX）
     */
    function saveOrder(tbody) {
        // 获取证据清单 ID
        const form = tbody.closest('form');
        if (!form) return;

        // 从 URL 获取清单 ID
        const match = window.location.pathname.match(/\/(\d+)\/change\//);
        if (!match) return;

        const listId = match[1];

        // 收集明细 ID
        const itemIds = [];
        const rows = tbody.querySelectorAll('tr.form-row:not(.empty-form)');
        rows.forEach(function(row) {
            const idInput = row.querySelector('input[name$="-id"]');
            if (idInput && idInput.value) {
                itemIds.push(parseInt(idInput.value));
            }
        });

        if (itemIds.length === 0) return;

        // 发送 AJAX 请求
        const url = `/admin/documents/evidencelist/${listId}/reorder/`;
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ item_ids: itemIds })
        })
        .then(function(response) {
            if (!response.ok) {
                throw new Error('保存失败');
            }
            return response.json();
        })
        .then(function(data) {
            if (data.success) {
                showMessage('排序已保存', 'success');
            } else {
                showMessage(data.error || '保存失败', 'error');
            }
        })
        .catch(function(error) {
            console.error('保存排序失败:', error);
            showMessage('保存排序失败', 'error');
        });
    }

    /**
     * 获取 CSRF Token
     */
    function getCSRFToken() {
        return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
    }

    /**
     * 显示消息
     */
    function showMessage(message, type) {
        // 使用 Django Admin 的消息系统
        const messagesContainer = document.querySelector('.messagelist');
        if (messagesContainer) {
            const li = document.createElement('li');
            li.className = type;
            li.textContent = message;
            messagesContainer.appendChild(li);

            // 3秒后自动移除
            setTimeout(function() {
                li.remove();
            }, 3000);
        } else {
            // 创建临时消息
            const div = document.createElement('div');
            div.className = 'evidence-message ' + type;
            div.textContent = message;
            div.style.cssText = 'position: fixed; top: 20px; right: 20px; padding: 10px 20px; border-radius: 4px; z-index: 9999;';
            div.style.backgroundColor = type === 'success' ? '#4caf50' : '#f44336';
            div.style.color = 'white';
            document.body.appendChild(div);

            setTimeout(function() {
                div.remove();
            }, 3000);
        }
    }

})();
