/**
 * 文件夹绑定通用 Alpine.js 组件
 * 功能：文件夹路径绑定、状态显示、绑定管理
 * 支持：案件、合同模块
 *
 * @deprecated 原始文件 folder_binding.js 已废弃，请使用此 Alpine.js 组件
 */

/**
 * 文件夹绑定 Alpine.js 组件
 * @param {Object} config - 配置参数
 * @param {string} config.entityType - 实体类型 ('case' | 'contract')
 * @param {string} config.apiBasePath - API 基础路径 (如 '/api/v1/cases' 或 '/api/v1/contracts')
 * @param {string} config.urlPattern - URL 匹配模式 (用于从 URL 提取实体 ID)
 * @returns {Object} Alpine 组件对象
 */
function folderBindingApp(config = {}) {
    return {
        // ========== 配置参数 ==========
        entityType: config.entityType || 'case',
        apiBasePath: config.apiBasePath || '/api/v1/cases',
        urlPattern: config.urlPattern || /\/admin\/cases\/case\/(\d+)\/change\//,
        enableBrowse: !!config.enableBrowse,

        // ========== 状态 ==========
        entityId: null,              // 实体 ID (案件/合同)
        entityData: null,            // 实体数据缓存
        currentBinding: null,        // 当前绑定信息
        isLoading: false,            // 加载状态
        isSaving: false,             // 保存状态
        isDialogOpen: false,         // 对话框显示状态
        isUpdatingBinding: false,    // 是否为更新操作
        folderPath: '',              // 输入的文件夹路径
        errorMessage: '',            // 错误信息
        successMessage: '',

        isBrowseOpen: false,
        isBrowsing: false,
        browsePath: null,
        browseParentPath: null,
        browseRoots: [],
        browseRecent: [],
        browseEntriesAll: [],
        browseEntries: [],
        browseSearch: '',
        browseShowHidden: false,
        browsePathInput: '',
        browseSelectedPath: null,
        browseSelectedIndex: -1,
        browseMessage: '',
        browseError: '',

        // 文件模板检查状态
        hasMatchedFolderTemplates: false,
        matchedFolderTemplates: [],
        isCheckingFolderTemplates: true,
        folderNoMatchReason: '',          // 成功信息
        _initialized: false,              // 防止重复初始化

        async init() {
            // 防止重复初始化
            if (this._initialized) return;
            this._initialized = true;

            // 从 URL 提取实体 ID
            this.entityId = this.extractEntityId();

            if (this.entityId) {
                // 尝试从全局缓存获取实体数据（避免重复请求）
                const cacheKey = `${this.entityType}_${this.entityId}`;
                if (window._entityDataCache && window._entityDataCache[cacheKey]) {
                    this.entityData = window._entityDataCache[cacheKey];
                    // 只需要加载绑定状态
                    await this.loadBindingStatus();
                } else {
                    // 并行加载绑定状态和实体数据
                    await Promise.all([
                        this.loadBindingStatus(),
                        this.loadEntityData()
                    ]);
                    // 缓存实体数据供其他组件使用
                    if (this.entityData) {
                        window._entityDataCache = window._entityDataCache || {};
                        window._entityDataCache[cacheKey] = this.entityData;
                    }
                }
                // 实体数据加载完成后检查模板
                this.checkMatchedFolderTemplates();
            } else {
                console.error('无法获取实体ID');
            }

            // 监听键盘事件
            this.$watch('isDialogOpen', (open) => {
                if (open) {
                    // 对话框打开时添加 ESC 键监听
                    document.addEventListener('keydown', this.handleKeyDown.bind(this));
                } else {
                    document.removeEventListener('keydown', this.handleKeyDown.bind(this));
                }
            });
        },

        // ========== 工具方法 ==========

        /**
         * 从 URL 提取实体 ID
         */
        extractEntityId() {
            const match = window.location.pathname.match(this.urlPattern);
            return match ? match[1] : null;
        },

        /**
         * 获取 CSRF Token
         */
        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        /**
         * HTML 转义
         */
        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        /**
         * 格式化日期时间
         */
        formatDateTime(dateStr) {
            if (!dateStr) return '';
            return new Date(dateStr).toLocaleString('zh-CN');
        },

        /**
         * 处理键盘事件
         */
        handleKeyDown(e) {
            if (e.key === 'Escape' && this.isDialogOpen) {
                this.closeDialog();
            } else if (e.key === 'Enter' && this.isDialogOpen && !this.isSaving) {
                this.saveBinding();
            }
        },

        // ========== 计算属性 ==========

        /**
         * 是否已绑定
         */
        get isBound() {
            return this.currentBinding !== null;
        },

        /**
         * 绑定状态文本
         */
        get bindingStatusText() {
            if (this.isLoading) {
                return '正在加载...';
            }
            if (!this.currentBinding) {
                return '未绑定';
            }
            const displayPath = this.currentBinding.folder_path_display || this.currentBinding.folder_path;
            return `已绑定：${displayPath}`;
        },

        /**
         * 绑定时间文本
         */
        get bindingTimeText() {
            if (!this.currentBinding || !this.currentBinding.created_at) {
                return '';
            }
            return `绑定时间：${this.formatDateTime(this.currentBinding.created_at)}`;
        },

        /**
         * 对话框标题
         */
        get dialogTitle() {
            return this.isUpdatingBinding ? '更换文件夹' : '绑定文件夹';
        },

        get browseBreadcrumbs() {
            if (!this.browsePath) return [];
            const p = String(this.browsePath);
            if (p.startsWith('/')) {
                const parts = p.split('/').filter(Boolean);
                const crumbs = [{ name: '/', path: '/' }];
                let acc = '';
                for (const part of parts) {
                    acc = acc + '/' + part;
                    crumbs.push({ name: part, path: acc });
                }
                return crumbs;
            }
            const m = p.match(/^([A-Za-z]:\\)(.*)$/);
            if (m) {
                const drive = m[1];
                const rest = m[2] || '';
                const parts = rest.split('\\').filter(Boolean);
                const crumbs = [{ name: drive, path: drive }];
                let acc = drive.endsWith('\\') ? drive.slice(0, -1) : drive;
                for (const part of parts) {
                    acc = `${acc}\\${part}`;
                    crumbs.push({ name: part, path: acc });
                }
                return crumbs;
            }
            return [{ name: p, path: p }];
        },

        // ========== API 方法 ==========

        /**
         * 加载实体数据（案件/合同）
         */
        async loadEntityData() {
            if (!this.entityId) return;

            // 先检查全局缓存
            const cacheKey = `${this.entityType}_${this.entityId}`;
            if (window._entityDataCache && window._entityDataCache[cacheKey]) {
                this.entityData = window._entityDataCache[cacheKey];
                return;
            }

            try {
                const response = await fetch(`${this.apiBasePath}/${this.entityType}/${this.entityId}`);
                if (response.ok) {
                    this.entityData = await response.json();
                    // 缓存数据
                    window._entityDataCache = window._entityDataCache || {};
                    window._entityDataCache[cacheKey] = this.entityData;
                }
            } catch (error) {
                console.error('加载实体数据失败:', error);
                this.entityData = null;
            }
        },

        /**
         * 加载绑定状态
         */
        async loadBindingStatus() {
            if (!this.entityId) return;

            this.isLoading = true;
            this.errorMessage = '';

            try {
                const response = await fetch(`${this.apiBasePath}/${this.entityId}/folder-binding`);

                if (response.ok) {
                    this.currentBinding = await response.json();
                } else if (response.status === 404) {
                    this.currentBinding = null;
                } else {
                    throw new Error('获取绑定状态失败');
                }
            } catch (error) {
                console.error('加载绑定状态失败:', error);
                this.currentBinding = null;
            } finally {
                this.isLoading = false;
            }
        },

        /**
         * 保存绑定
         */
        async saveBinding() {
            // 验证路径
            const validationError = this.validateFolderPath(this.folderPath);
            if (validationError) {
                this.errorMessage = validationError;
                return;
            }

            if (!this.entityId) {
                this.errorMessage = '无法获取实体ID';
                return;
            }

            this.isSaving = true;
            this.errorMessage = '';

            try {
                const response = await fetch(`${this.apiBasePath}/${this.entityId}/folder-binding`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({
                        folder_path: this.folderPath.trim()
                    })
                });

                if (response.ok) {
                    this.currentBinding = await response.json();
                    this.closeDialog();
                    this.showSuccess(this.isUpdatingBinding ? '文件夹更换成功' : '文件夹绑定成功');
                } else {
                    const data = await response.json();
                    throw new Error(data.message || '操作失败');
                }
            } catch (error) {
                console.error('绑定操作失败:', error);
                this.errorMessage = error.message;
            } finally {
                this.isSaving = false;
            }
        },

        /**
         * 解除绑定
         */
        async removeBinding() {
            if (!confirm('确定要解除文件夹绑定吗？')) {
                return;
            }

            if (!this.entityId) {
                alert('无法获取实体ID');
                return;
            }

            this.isSaving = true;

            try {
                const response = await fetch(`${this.apiBasePath}/${this.entityId}/folder-binding`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    }
                });

                if (response.ok) {
                    this.currentBinding = null;
                    this.showSuccess('文件夹绑定已解除');
                } else {
                    throw new Error('解除绑定失败');
                }
            } catch (error) {
                console.error('解除绑定失败:', error);
                alert('解除绑定失败：' + error.message);
            } finally {
                this.isSaving = false;
            }
        },

        // ========== 对话框方法 ==========

        /**
         * 打开绑定对话框
         */
        openDialog(isUpdate = false) {
            this.isUpdatingBinding = isUpdate;
            this.folderPath = isUpdate && this.currentBinding ? this.currentBinding.folder_path : '';
            this.errorMessage = '';
            this.isDialogOpen = true;
            this.isBrowseOpen = false;
            this.browseSearch = '';
            this.browseMessage = '';
            this.browseError = '';
            this.loadBrowseRecent();

            // 延迟聚焦输入框
            this.$nextTick(() => {
                const input = this.$refs.folderPathInput;
                if (input) {
                    input.focus();
                }
            });
        },

        /**
         * 关闭对话框
         */
        closeDialog() {
            this.isDialogOpen = false;
            this.folderPath = '';
            this.errorMessage = '';
            this.isBrowseOpen = false;
            this.isBrowsing = false;
            this.browsePath = null;
            this.browseParentPath = null;
            this.browseRoots = [];
            this.browseRecent = [];
            this.browseEntriesAll = [];
            this.browseEntries = [];
            this.browseSearch = '';
            this.browseShowHidden = false;
            this.browsePathInput = '';
            this.browseSelectedPath = null;
            this.browseSelectedIndex = -1;
            this.browseMessage = '';
            this.browseError = '';
        },

        /**
         * 点击遮罩层关闭
         */
        handleOverlayClick(e) {
            if (e.target === e.currentTarget) {
                this.closeDialog();
            }
        },

        // ========== 路径处理方法 ==========

        /**
         * 验证文件夹路径
         */
        validateFolderPath(path) {
            if (!path || !path.trim()) {
                return '请输入文件夹路径';
            }

            const trimmedPath = path.trim();

            // 基本格式验证
            const patterns = [
                /^\/[^<>:"|?*]*$/,           // macOS/Linux 路径
                /^[A-Za-z]:\\[^<>:"|?*]*$/,  // Windows 路径
                /^\\\\[^\\]+\\[^<>:"|?*]*$/, // UNC 路径
                /^smb:\/\/[^\/]+\/[^<>:"|?*]*$/ // SMB 路径
            ];

            const isValid = patterns.some(pattern => pattern.test(trimmedPath));

            if (!isValid) {
                return '请输入有效的文件夹路径格式';
            }

            return null;
        },

        /**
         * 设置快捷路径
         */
        setQuickPath(path) {
            this.folderPath = path;
            this.$nextTick(() => {
                const input = this.$refs.folderPathInput;
                if (input) {
                    input.focus();
                }
            });
        },

        /**
         * 清空路径
         */
        clearPath() {
            this.folderPath = '';
            this.errorMessage = '';
            this.$nextTick(() => {
                const input = this.$refs.folderPathInput;
                if (input) {
                    input.focus();
                }
            });
        },

        toggleBrowse() {
            if (!this.enableBrowse) return;
            this.isBrowseOpen = !this.isBrowseOpen;
            if (this.isBrowseOpen) {
                this.browseSearch = '';
                this.browseSelectedPath = null;
                this.browseSelectedIndex = -1;
                const startPath = (this.folderPath || '').trim();
                this.loadBrowse(startPath || null);
            }
        },

        setFolderPath(path) {
            this.folderPath = String(path || '');
            this.errorMessage = '';
            this.recordBrowseRecent(this.folderPath);
            this.$nextTick(() => {
                const input = this.$refs.folderPathInput;
                if (input) input.focus();
            });
        },

        loadBrowseRecent() {
            try {
                const key = `folder_binding_recent:${this.apiBasePath}`;
                const raw = window.localStorage ? window.localStorage.getItem(key) : null;
                const data = raw ? JSON.parse(raw) : [];
                this.browseRecent = Array.isArray(data) ? data.filter(Boolean).slice(0, 10) : [];
            } catch (_) {
                this.browseRecent = [];
            }
        },

        recordBrowseRecent(path) {
            const p = String(path || '').trim();
            if (!p) return;
            try {
                const key = `folder_binding_recent:${this.apiBasePath}`;
                const list = [p, ...this.browseRecent.filter((x) => x !== p)].slice(0, 10);
                this.browseRecent = list;
                if (window.localStorage) {
                    window.localStorage.setItem(key, JSON.stringify(list));
                }
            } catch (_) {}
        },

        applyBrowseFilter() {
            const q = String(this.browseSearch || '').trim().toLowerCase();
            if (!q) {
                this.browseEntries = this.browseEntriesAll.slice();
                return;
            }
            this.browseEntries = this.browseEntriesAll.filter((e) => {
                const name = (e && e.name) ? String(e.name).toLowerCase() : '';
                return name.includes(q);
            });
            this.browseSelectedIndex = -1;
            this.browseSelectedPath = null;
        },

        async loadBrowse(path) {
            if (!this.enableBrowse) return;
            this.isBrowsing = true;
            this.browseError = '';
            this.browseMessage = '';
            this.browseSelectedIndex = -1;
            this.browseSelectedPath = null;

            try {
                const baseUrl = `${this.apiBasePath}/folder-browse`;
                const params = [];
                if (path) params.push(`path=${encodeURIComponent(path)}`);
                if (this.browseShowHidden) params.push('include_hidden=true');
                const url = params.length ? `${baseUrl}?${params.join('&')}` : baseUrl;
                const response = await fetch(url, {
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    }
                });

                if (!response.ok) {
                    let msg = '加载目录失败';
                    try {
                        const data = await response.json();
                        if (data && (data.detail || data.message)) msg = data.detail || data.message;
                    } catch (_) {}
                    throw new Error(msg);
                }

                const data = await response.json();
                const entries = Array.isArray(data.entries) ? data.entries : [];
                this.browseEntriesAll = entries;
                this.browseEntries = entries.slice();
                this.browsePath = data.path || null;
                this.browseParentPath = data.parent_path || null;
                this.browseMessage = data.browsable ? '' : (data.message || '该路径不支持浏览');
                this.browsePathInput = this.browsePath || '';
                if (!this.browsePath) {
                    this.browseRoots = this.browseEntries.slice();
                }
                this.applyBrowseFilter();
            } catch (error) {
                this.browseError = error.message || '加载目录失败';
                this.browseEntriesAll = [];
                this.browseEntries = [];
                this.browsePath = null;
                this.browseParentPath = null;
            } finally {
                this.isBrowsing = false;
            }
        },

        reloadBrowse() {
            this.loadBrowse(this.browsePath || null);
        },

        browseInto(path) {
            this.loadBrowse(path);
        },

        browseUp() {
            if (this.browseParentPath) {
                this.loadBrowse(this.browseParentPath);
            } else {
                this.loadBrowse(null);
            }
        },

        browseGoPathInput() {
            const p = String(this.browsePathInput || '').trim();
            if (!p) {
                this.loadBrowse(null);
                return;
            }
            this.loadBrowse(p);
        },

        browseSelect(entry, index) {
            this.browseSelectedIndex = typeof index === 'number' ? index : -1;
            this.browseSelectedPath = entry && entry.path ? String(entry.path) : null;
        },

        browseChooseSelected() {
            if (this.browseSelectedPath) {
                this.setFolderPath(this.browseSelectedPath);
                this.isBrowseOpen = false;
            }
        },

        chooseBrowsePath() {
            if (this.browsePath) {
                this.setFolderPath(this.browsePath);
                this.isBrowseOpen = false;
            }
        },

        handleBrowseKeyDown(e) {
            if (!this.isBrowseOpen) return;
            if (!this.browseEntries || !this.browseEntries.length) return;
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                const next = Math.min(this.browseEntries.length - 1, (this.browseSelectedIndex < 0 ? 0 : this.browseSelectedIndex + 1));
                this.browseSelect(this.browseEntries[next], next);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                const prev = Math.max(0, (this.browseSelectedIndex < 0 ? 0 : this.browseSelectedIndex - 1));
                this.browseSelect(this.browseEntries[prev], prev);
            } else if (e.key === 'Enter') {
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    this.browseChooseSelected();
                    return;
                }
                if (this.browseSelectedIndex >= 0) {
                    e.preventDefault();
                    const entry = this.browseEntries[this.browseSelectedIndex];
                    if (entry && entry.path) this.browseInto(entry.path);
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                this.isBrowseOpen = false;
            }
        },

        // ========== 模板检查 ==========

        /**
         * 检查匹配的文件夹模板（使用缓存的实体数据）
         */
        async checkMatchedFolderTemplates() {
            if (!this.entityId) return;

            this.isCheckingFolderTemplates = true;

            try {
                // 使用缓存的实体数据
                if (!this.entityData) {
                    this.matchedFolderTemplates = [];
                    this.hasMatchedFolderTemplates = false;
                    this.folderNoMatchReason = '获取实体信息失败';
                    return;
                }

                // 根据实体类型获取案由或合同类型
                let causeOfAction = null;
                if (this.entityType === 'case') {
                    causeOfAction = this.entityData.cause_of_action;
                } else {
                    causeOfAction = this.entityData.case_type;
                }

                if (!causeOfAction) {
                    this.matchedFolderTemplates = [];
                    this.hasMatchedFolderTemplates = false;
                    this.folderNoMatchReason = this.entityType === 'case' ? '案件未设置案由' : '合同未设置类型';
                    return;
                }

                // 获取匹配的文件夹模板
                const templatesResponse = await fetch(`/api/v1/documents/folder-templates?cause_of_action=${encodeURIComponent(causeOfAction)}`);
                if (!templatesResponse.ok) {
                    throw new Error('获取模板列表失败');
                }
                const templates = await templatesResponse.json();

                this.matchedFolderTemplates = templates.filter(t => t.is_active !== false);
                this.hasMatchedFolderTemplates = this.matchedFolderTemplates.length > 0;

                if (!this.hasMatchedFolderTemplates) {
                    this.folderNoMatchReason = `「${causeOfAction}」暂无配置文件夹模板`;
                }

            } catch (error) {
                console.error('检查文件夹模板失败:', error);
                this.hasMatchedFolderTemplates = false;
                this.matchedFolderTemplates = [];
                this.folderNoMatchReason = '检查模板失败';
            } finally {
                this.isCheckingFolderTemplates = false;
            }
        },

        // ========== 消息提示 ==========

        /**
         * 显示成功消息
         */
        showSuccess(message) {
            this.successMessage = message;

            // 3秒后自动清除
            setTimeout(() => {
                this.successMessage = '';
            }, 3000);
        }
    };
}

// 导出到全局作用域
window.folderBindingApp = folderBindingApp;
