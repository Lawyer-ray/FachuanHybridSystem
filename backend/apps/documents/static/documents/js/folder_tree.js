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
/**
 * ID验证管理器
 * 提供实时ID重复检测功能
 */
(function() {
    'use strict';

    // ID验证管理器类
    class IDValidationManager {
        constructor() {
            this.debounceTimer = null;
            this.debounceDelay = 500;
            this.validateUrl = '/admin/documents/foldertemplate/validate-structure/';
            this.duplicateReportUrl = '/admin/documents/foldertemplate/duplicate-report/';
            this.init();
        }

        init() {
            // 等待DOM加载完成
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => this.setupValidation());
            } else {
                this.setupValidation();
            }
        }

        setupValidation() {
            const structureField = document.querySelector('#id_structure');
            if (!structureField) return;

            this.createValidationUI(structureField);
            this.bindEvents(structureField);
        }

        createValidationUI(structureField) {
            // 创建验证状态显示区域
            const validationDiv = document.createElement('div');
            validationDiv.id = 'structure-validation';
            validationDiv.className = 'validation-status';
            validationDiv.style.marginTop = '10px';
            validationDiv.innerHTML = `
                <div class="validation-message"></div>
                <div class="validation-loading" style="display: none;">
                    <span>🔄 正在验证ID唯一性...</span>
                </div>
            `;

            // 创建重复报告按钮
            const reportBtn = document.createElement('button');
            reportBtn.type = 'button';
            reportBtn.className = 'duplicate-report-btn';
            reportBtn.style.cssText = 'margin-top: 10px; padding: 5px 10px; background: #007cba; color: white; border: none; border-radius: 3px; cursor: pointer;';
            reportBtn.textContent = '📊 查看重复ID报告';

            // 插入到结构字段后面
            const fieldContainer = structureField.closest('.form-row') || structureField.parentNode;
            fieldContainer.appendChild(validationDiv);
            fieldContainer.appendChild(reportBtn);

            // 绑定报告按钮事件
            reportBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.showDuplicateReport();
            });
        }

        bindEvents(structureField) {
            // 监听结构字段变化
            structureField.addEventListener('input', () => {
                this.handleStructureChange(structureField);
            });

            // 监听表单提交
            const form = structureField.closest('form');
            if (form) {
                form.addEventListener('submit', (e) => {
                    this.handleFormSubmit(e);
                });
            }
        }

        handleStructureChange(structureField) {
            const structureText = structureField.value.trim();

            if (!structureText) {
                this.clearValidationStatus();
                return;
            }

            try {
                const structure = JSON.parse(structureText);
                const templateId = this.getTemplateId();

                this.showValidationLoading();
                this.debounceValidate(structure, templateId);

            } catch (error) {
                this.showValidationResult({
                    isValid: false,
                    errors: ['JSON格式错误: ' + error.message]
                });
            }
        }

        debounceValidate(structure, templateId) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(() => {
                this.validateStructure(structure, templateId)
                    .then(result => this.showValidationResult(result))
                    .catch(error => {
                        console.error('验证失败:', error);
                        this.showValidationResult({
                            isValid: false,
                            errors: [error.message || '验证请求失败']
                        });
                    });
            }, this.debounceDelay);
        }

        validateStructure(structure, templateId = null) {
            return new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open('POST', this.validateUrl, true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-CSRFToken', this.getCSRFToken());

                xhr.onload = function() {
                    if (xhr.status === 200) {
                        try {
                            const response = JSON.parse(xhr.responseText);
                            if (response.success) {
                                resolve({
                                    isValid: response.is_valid,
                                    errors: response.errors || []
                                });
                            } else {
                                reject(new Error(response.message || '验证失败'));
                            }
                        } catch (e) {
                            reject(new Error('响应解析失败'));
                        }
                    } else {
                        reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                    }
                };

                xhr.onerror = function() {
                    reject(new Error('网络请求失败'));
                };

                xhr.send(JSON.stringify({
                    structure: structure,
                    template_id: templateId
                }));
            });
        }

        getTemplateId() {
            // 从URL获取模板ID
            const urlMatch = window.location.pathname.match(/\/(\d+)\/change\//);
            return urlMatch ? parseInt(urlMatch[1]) : null;
        }

        getCSRFToken() {
            if (window.FachuanCSRF && window.FachuanCSRF.getToken) return window.FachuanCSRF.getToken() || '';
            const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
            return tokenInput ? tokenInput.value : '';
        }

        showValidationLoading() {
            const validationDiv = document.querySelector('#structure-validation');
            if (validationDiv) {
                validationDiv.querySelector('.validation-loading').style.display = 'block';
                validationDiv.querySelector('.validation-message').style.display = 'none';
            }
        }

        showValidationResult(result) {
            const validationDiv = document.querySelector('#structure-validation');
            if (!validationDiv) return;

            const messageDiv = validationDiv.querySelector('.validation-message');
            const loadingDiv = validationDiv.querySelector('.validation-loading');

            loadingDiv.style.display = 'none';
            messageDiv.style.display = 'block';

            if (result.isValid) {
                validationDiv.className = 'validation-status valid';
                messageDiv.innerHTML = '<span style="color: green;">✅ 文件夹结构ID验证通过</span>';
            } else {
                validationDiv.className = 'validation-status invalid';
                const errorHtml = result.errors.map(error =>
                    `<div style="color: red; margin: 2px 0;">❌ ${this.escapeHtml(error)}</div>`
                ).join('');
                messageDiv.innerHTML = errorHtml;
            }
        }

        clearValidationStatus() {
            const validationDiv = document.querySelector('#structure-validation');
            if (validationDiv) {
                validationDiv.className = 'validation-status';
                validationDiv.querySelector('.validation-message').style.display = 'none';
                validationDiv.querySelector('.validation-loading').style.display = 'none';
            }
        }

        handleFormSubmit(e) {
            // 不再阻止提交，让后端的 FolderTemplateForm.clean_structure() 自动修复重复ID
            // 后端会自动修复重复ID并显示成功消息
            const validationDiv = document.querySelector('#structure-validation');
            if (validationDiv && validationDiv.classList.contains('invalid')) {
                // 显示提示信息，告知用户后端会自动修复
                const messageDiv = validationDiv.querySelector('.validation-message');
                if (messageDiv) {
                    messageDiv.innerHTML = '<span style="color: #856404;">⏳ 正在提交，后端将自动修复重复ID...</span>';
                }
            }
        }

        showDuplicateReport() {
            const xhr = new XMLHttpRequest();
            xhr.open('GET', this.duplicateReportUrl, true);
            xhr.setRequestHeader('X-CSRFToken', this.getCSRFToken());

            xhr.onload = () => {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            this.displayDuplicateReport(response.report);
                        } else {
                            alert('获取报告失败: ' + response.error);
                        }
                    } catch (e) {
                        alert('响应解析失败');
                    }
                } else {
                    alert(`网络错误: HTTP ${xhr.status}`);
                }
            };

            xhr.onerror = () => {
                alert('网络请求失败');
            };

            xhr.send();
        }

        displayDuplicateReport(report) {
            let html = `
                <div class="duplicate-report" style="padding: 20px; max-height: 400px; overflow-y: auto;">
                    <h3 style="margin-top: 0;">📊 重复ID报告</h3>
                    <div style="background: #f5f5f5; padding: 10px; border-radius: 5px; margin: 10px 0;">
                        <p><strong>总模板数:</strong> ${report.total_templates}</p>
                        <p><strong>唯一ID数:</strong> ${report.total_unique_ids}</p>
                        <p><strong>重复ID数:</strong> ${report.duplicate_count}</p>
                    </div>
            `;

            if (report.duplicate_count > 0) {
                html += '<h4 style="color: red;">🚨 重复详情:</h4><ul style="max-height: 200px; overflow-y: auto;">';
                for (const [id, templates] of Object.entries(report.duplicates)) {
                    html += `<li style="margin: 5px 0;"><strong>${this.escapeHtml(id)}</strong>: ${templates.map(t => this.escapeHtml(t)).join(', ')}</li>`;
                }
                html += '</ul>';
            } else {
                html += '<p style="color: green; font-weight: bold;">✅ 未发现重复ID</p>';
            }

            html += '</div>';

            // 创建模态框
            this.showModal('重复ID报告', html);
        }

        showModal(title, content) {
            // 创建遮罩层
            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.5); z-index: 10000; display: flex;
                align-items: center; justify-content: center;
            `;

            // 创建模态框
            const modal = document.createElement('div');
            modal.style.cssText = `
                background: white; border-radius: 8px; max-width: 600px; width: 90%;
                max-height: 80vh; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            `;

            modal.innerHTML = `
                <div style="padding: 15px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0;">${this.escapeHtml(title)}</h3>
                    <button class="close-modal" style="background: none; border: none; font-size: 24px; cursor: pointer; color: #666;">&times;</button>
                </div>
                <div style="overflow-y: auto; max-height: calc(80vh - 80px);">
                    ${content}
                </div>
                <div style="padding: 15px; border-top: 1px solid #ddd; text-align: right;">
                    <button class="close-modal" style="padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;">关闭</button>
                </div>
            `;

            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            // 绑定关闭事件
            const closeButtons = modal.querySelectorAll('.close-modal');
            closeButtons.forEach(btn => {
                btn.addEventListener('click', () => {
                    document.body.removeChild(overlay);
                });
            });

            // 点击遮罩层关闭
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    document.body.removeChild(overlay);
                }
            });
        }

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    }

    // 初始化ID验证管理器
    new IDValidationManager();

})();
