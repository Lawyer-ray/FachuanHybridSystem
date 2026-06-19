/**
 * 文件夹模板拖拽编辑器
 *
 * 使用 SortableJS 实现嵌套列表的拖拽排序
 *
 * Requirements: 6.3, 6.4
 */

(function() {
    'use strict';

    // 防止重复初始化
    if (window._folderEditorInitialized) {
        return;
    }
    window._folderEditorInitialized = true;

    // 等待 DOM 加载完成
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFolderEditor);
    } else {
        initFolderEditor();
    }

    /**
     * 初始化文件夹编辑器
     */
    function initFolderEditor() {
        const structureField = document.querySelector('#id_structure');
        if (!structureField) return;

        // 检查是否已经初始化
        if (document.querySelector('.folder-editor-container')) {
            return;
        }

        // 等待 SortableJS 加载
        waitForSortable(function() {
            createEditor(structureField);
        });
    }

    /**
     * 等待 SortableJS 加载
     */
    function waitForSortable(callback, attempts) {
        attempts = attempts || 0;

        if (typeof Sortable !== 'undefined') {
            callback();
            return;
        }

        if (attempts > 50) {
            console.error('SortableJS 加载超时');
            // 仍然创建编辑器，但拖拽功能不可用
            callback();
            return;
        }

        setTimeout(function() {
            waitForSortable(callback, attempts + 1);
        }, 100);
    }

    /**
     * 创建编辑器
     */
    function createEditor(structureField) {
        // 创建编辑器容器
        const editorContainer = createEditorContainer();

        // 找到 structure 字段的父容器
        const fieldRow = structureField.closest('.form-row') || structureField.parentNode;
        fieldRow.appendChild(editorContainer);

        // 解析现有结构
        let structure = {};
        try {
            const value = structureField.value || '{}';
            structure = JSON.parse(value);
        } catch (e) {
            console.warn('无法解析文件夹结构:', e);
            structure = { children: [] };
        }

        // 渲染可拖拽列表
        const rootList = editorContainer.querySelector('.sortable-folder-list');
        renderFolderList(rootList, structure);

        // 初始化 SortableJS
        if (typeof Sortable !== 'undefined') {
            initSortableInstances(editorContainer);
        }

        // 绑定事件
        bindEvents(editorContainer, structureField);
    }

    /**
     * 创建编辑器容器
     */
    function createEditorContainer() {
        const container = document.createElement('div');
        container.className = 'folder-editor-container';
        container.innerHTML = `
            <div class="folder-editor-header">
                <h3>文件夹结构编辑器</h3>
                <div class="folder-editor-actions">
                    <button type="button" class="add-root-folder btn">+ 添加根文件夹</button>
                    <button type="button" class="expand-all btn">展开全部</button>
                    <button type="button" class="collapse-all btn">折叠全部</button>
                </div>
            </div>
            <div class="sortable-folder-list" data-level="0">
                <span class="empty-hint">暂无文件夹</span>
            </div>
            <div class="add-folder-input" style="display: none;">
                <input type="text" placeholder="输入文件夹名称" class="new-folder-name">
                <button type="button" class="confirm-add btn">添加</button>
                <button type="button" class="cancel-add btn">取消</button>
            </div>
            <div class="save-status" style="display: none;"></div>
        `;
        return container;
    }

    /**
     * 渲染文件夹列表
     */
    function renderFolderList(container, structure, level) {
        level = level || 0;
        const children = structure.children || [];

        if (children.length === 0) {
            container.innerHTML = '<span class="empty-hint">暂无文件夹</span>';
            container.classList.add('empty');
            return;
        }

        container.classList.remove('empty');
        container.innerHTML = '';

        children.forEach(function(child) {
            // 确保每个文件夹都有唯一 ID
            if (!child.id) {
                child.id = generateUniqueId(container.closest('.folder-editor-container'));
            }

            const item = createFolderItem(child, level);
            container.appendChild(item);

            // 递归渲染子文件夹
            if (child.children && child.children.length > 0) {
                const nestedList = item.querySelector('.nested-list');
                renderFolderList(nestedList, child, level + 1);
            }
        });
    }

    /**
     * 创建文件夹项
     */
    function createFolderItem(folder, level) {
        const item = document.createElement('div');
        item.className = 'sortable-folder-item';
        item.dataset.id = folder.id || generateUniqueId();
        item.dataset.level = level;

        const hasChildren = folder.children && folder.children.length > 0;

        item.innerHTML = `
            <div class="folder-item-content">
                <span class="folder-toggle">${hasChildren ? '▼' : '▶'}</span>
                <span class="folder-icon" title="拖拽移动">▣</span>
                <span class="folder-name">
                    <input type="text" value="${escapeHtml(folder.name || '')}" placeholder="文件夹名称">
                </span>
                <div class="folder-actions">
                    <button type="button" class="add-child btn-small" title="添加子文件夹">+</button>
                    <button type="button" class="delete btn-small" title="删除">×</button>
                </div>
            </div>
            <div class="nested-list sortable-folder-list" data-level="${level + 1}">
                <span class="empty-hint">暂无子文件夹</span>
            </div>
        `;

        return item;
    }

    /**
     * 初始化所有可排序列表
     */
    function initSortableInstances(container) {
        if (typeof Sortable === 'undefined') {
            console.warn('SortableJS 未加载，拖拽功能不可用');
            return;
        }

        const lists = container.querySelectorAll('.sortable-folder-list');

        lists.forEach(function(list) {
            if (list._sortable) return; // 避免重复初始化

            list._sortable = new Sortable(list, {
                group: 'folders',
                animation: 150,
                fallbackOnBody: true,
                swapThreshold: 0.65,
                ghostClass: 'sortable-ghost',
                chosenClass: 'sortable-chosen',
                dragClass: 'sortable-drag',
                handle: '.folder-icon',
                filter: '.empty-hint',
                onEnd: function() {
                    updateStructureField(container);
                    updateEmptyHints(container);
                }
            });
        });
    }

    /**
     * 绑定事件
     */
    function bindEvents(container, structureField) {
        // 添加根文件夹
        container.querySelector('.add-root-folder').addEventListener('click', function(e) {
            e.preventDefault();
            showAddInput(container, container.querySelector('.sortable-folder-list[data-level="0"]'));
        });

        // 展开全部
        container.querySelector('.expand-all').addEventListener('click', function(e) {
            e.preventDefault();
            container.querySelectorAll('.nested-list').forEach(function(list) {
                list.style.display = 'block';
            });
            container.querySelectorAll('.folder-toggle').forEach(function(toggle) {
                toggle.textContent = '▼';
            });
        });

        // 折叠全部
        container.querySelector('.collapse-all').addEventListener('click', function(e) {
            e.preventDefault();
            container.querySelectorAll('.nested-list').forEach(function(list) {
                list.style.display = 'none';
            });
            container.querySelectorAll('.folder-toggle').forEach(function(toggle) {
                toggle.textContent = '▶';
            });
        });

        // 事件委托处理文件夹操作
        container.addEventListener('click', function(e) {
            const target = e.target;

            // 展开/折叠
            if (target.classList.contains('folder-toggle')) {
                e.preventDefault();
                const item = target.closest('.sortable-folder-item');
                const nestedList = item.querySelector('.nested-list');
                if (nestedList.style.display === 'none') {
                    nestedList.style.display = 'block';
                    target.textContent = '▼';
                } else {
                    nestedList.style.display = 'none';
                    target.textContent = '▶';
                }
            }

            // 添加子文件夹
            if (target.classList.contains('add-child')) {
                e.preventDefault();
                const item = target.closest('.sortable-folder-item');
                const nestedList = item.querySelector('.nested-list');
                nestedList.style.display = 'block';
                item.querySelector('.folder-toggle').textContent = '▼';
                showAddInput(container, nestedList);
            }

            // 删除文件夹
            if (target.classList.contains('delete')) {
                e.preventDefault();
                if (confirm('确定要删除此文件夹及其所有子文件夹吗？')) {
                    const item = target.closest('.sortable-folder-item');
                    item.remove();
                    updateStructureField(container);
                    updateEmptyHints(container);
                }
            }

            // 确认添加
            if (target.classList.contains('confirm-add')) {
                e.preventDefault();
                confirmAddFolder(container);
            }

            // 取消添加
            if (target.classList.contains('cancel-add')) {
                e.preventDefault();
                hideAddInput(container);
            }
        });

        // 文件夹名称变更
        container.addEventListener('input', function(e) {
            if (e.target.matches('.folder-name input')) {
                updateStructureField(container);
            }
        });

        // 回车确认添加
        container.querySelector('.new-folder-name').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                confirmAddFolder(container);
            }
        });
    }

    /**
     * 显示添加输入框
     */
    var currentTargetList = null;
    function showAddInput(container, targetList) {
        currentTargetList = targetList;
        const inputArea = container.querySelector('.add-folder-input');
        const input = inputArea.querySelector('.new-folder-name');
        inputArea.style.display = 'flex';
        input.value = '';
        input.focus();
    }

    /**
     * 隐藏添加输入框
     */
    function hideAddInput(container) {
        const inputArea = container.querySelector('.add-folder-input');
        inputArea.style.display = 'none';
        currentTargetList = null;
    }

    /**
     * 确认添加文件夹
     */
    function confirmAddFolder(container) {
        const input = container.querySelector('.new-folder-name');
        const name = input.value.trim();

        if (!name) {
            alert('请输入文件夹名称');
            return;
        }

        // 验证文件夹名称
        const invalidChars = /[\/\\:*?"<>|]/;
        if (invalidChars.test(name)) {
            alert('文件夹名称不能包含以下字符: / \\ : * ? " < > |');
            return;
        }

        if (currentTargetList) {
            // 移除空提示
            const emptyHint = currentTargetList.querySelector(':scope > .empty-hint');
            if (emptyHint) emptyHint.remove();
            currentTargetList.classList.remove('empty');

            // 创建新文件夹项，确保 ID 唯一
            const level = parseInt(currentTargetList.dataset.level) || 0;
            const newFolder = { id: generateUniqueId(container), name: name, children: [] };
            const item = createFolderItem(newFolder, level);
            currentTargetList.appendChild(item);

            // 初始化新的嵌套列表的 Sortable
            if (typeof Sortable !== 'undefined') {
                const nestedList = item.querySelector('.nested-list');
                nestedList._sortable = new Sortable(nestedList, {
                    group: 'folders',
                    animation: 150,
                    fallbackOnBody: true,
                    swapThreshold: 0.65,
                    ghostClass: 'sortable-ghost',
                    chosenClass: 'sortable-chosen',
                    dragClass: 'sortable-drag',
                    handle: '.folder-icon',
                    filter: '.empty-hint',
                    onEnd: function() {
                        updateStructureField(container);
                        updateEmptyHints(container);
                    }
                });
            }

            updateStructureField(container);
        }

        hideAddInput(container);
    }

    /**
     * 更新结构字段
     */
    function updateStructureField(container) {
        const structureField = document.querySelector('#id_structure');
        if (!structureField) return;

        const rootList = container.querySelector('.sortable-folder-list[data-level="0"]');
        const structure = extractStructure(rootList);

        structureField.value = JSON.stringify(structure, null, 2);

        // 显示保存状态
        showSaveStatus(container, 'success', '结构已更新（保存后生效）');
    }

    /**
     * 从 DOM 提取结构
     */
    function extractStructure(list) {
        const children = [];
        const items = list.querySelectorAll(':scope > .sortable-folder-item');

        items.forEach(function(item) {
            const nameInput = item.querySelector('.folder-name input');
            const nestedList = item.querySelector('.nested-list');

            const folder = {
                id: item.dataset.id,
                name: nameInput ? nameInput.value : '',
                children: nestedList ? extractStructure(nestedList).children : []
            };

            children.push(folder);
        });

        return { children: children };
    }

    /**
     * 更新空提示
     */
    function updateEmptyHints(container) {
        container.querySelectorAll('.sortable-folder-list').forEach(function(list) {
            const items = list.querySelectorAll(':scope > .sortable-folder-item');
            const emptyHint = list.querySelector(':scope > .empty-hint');

            if (items.length === 0) {
                if (!emptyHint) {
                    const hint = document.createElement('span');
                    hint.className = 'empty-hint';
                    hint.textContent = list.dataset.level === '0' ? '暂无文件夹' : '暂无子文件夹';
                    list.appendChild(hint);
                }
                list.classList.add('empty');
            } else {
                if (emptyHint) emptyHint.remove();
                list.classList.remove('empty');
            }
        });
    }

    /**
     * 显示保存状态
     */
    function showSaveStatus(container, type, message) {
        const status = container.querySelector('.save-status');
        status.className = 'save-status ' + type;
        status.textContent = message;
        status.style.display = 'block';

        setTimeout(function() {
            status.style.display = 'none';
        }, 3000);
    }

    /**
     * 生成唯一 ID
     */
    function generateId() {
        return 'folder_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * 生成全局唯一 ID（检查重复）
     */
    function generateUniqueId(container) {
        let id;
        let attempts = 0;
        const maxAttempts = 100;

        do {
            id = generateId();
            attempts++;

            // 防止无限循环
            if (attempts > maxAttempts) {
                id = 'folder_' + Date.now() + '_' + attempts + '_' + Math.random().toString(36).substr(2, 9);
                break;
            }
        } while (container && container.querySelector(`[data-id="${id}"]`));

        return id;
    }

    /**
     * HTML 转义
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

})();
