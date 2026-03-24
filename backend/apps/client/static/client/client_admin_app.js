/**
 * 当事人管理 Alpine.js 组件
 * 功能：文本解析、表单填充
 * 替代原有的 admin.js (IIFE 模式)
 */
function clientAdminApp() {
    return {
        // ========== 状态 ==========
        isDialogOpen: false,        // 对话框显示状态
        parseText: '',              // 待解析文本
        parseMultiple: false,       // 是否解析多个当事人
        isParsing: false,           // 解析中状态
        parseResult: null,          // 解析结果（单个当事人）
        multipleResults: [],        // 多个当事人解析结果
        showMultipleResults: false, // 显示多选结果对话框
        errorMessage: '',           // 错误信息
        successMessage: '',         // 成功信息

        // ========== OA 导入状态 ==========
        oaImport: {
            showProgress: false,
            status: 'idle',  // idle / pending / in_progress / completed / failed
            phase: 'pending', // pending / discovering / importing / completed / failed
            sessionId: null,
            discoveredCount: 0,
            total: 0,
            processed: 0,
            successCount: 0,
            skipCount: 0,
            errorMessage: '',
            progressMessage: '',
        },
        oaHeadlessMode: true,
        oaImportOptions: {
            show: false,
            headless: true,
            importMode: 'all',  // all / partial
            limitValue: 100,
            anchorTop: 88,
            anchorRight: 24,
        },

        // ========== 初始化 ==========
        init() {
            console.log('[ClientAdminApp] 初始化当事人管理组件');
            window.__clientAdminAppInstance = this;
            this.initFormEnhancements();
            this.initPasteListener();
            this.initOAImportPreference();
            this.initOAImport();
        },

        // ========== 对话框管理 ==========

        /**
         * 打开文本解析对话框
         */
        openDialog() {
            this.isDialogOpen = true;
            this.resetState();
            // 延迟聚焦到文本框
            this.$nextTick(() => {
                const textarea = document.getElementById('parse-text-input');
                if (textarea) textarea.focus();
            });
        },

        /**
         * 关闭文本解析对话框
         */
        closeDialog() {
            this.isDialogOpen = false;
            this.resetState();
        },

        /**
         * 关闭多选结果对话框
         */
        closeMultipleResultsDialog() {
            this.showMultipleResults = false;
            this.multipleResults = [];
        },

        /**
         * 重置状态
         */
        resetState() {
            this.parseText = '';
            this.parseMultiple = false;
            this.isParsing = false;
            this.parseResult = null;
            this.errorMessage = '';
        },

        // ========== 文本解析 ==========

        /**
         * 解析当事人文本
         */
        async parseClientText() {
            if (!this.parseText.trim()) {
                this.showError('请输入要解析的文本内容');
                return;
            }

            this.isParsing = true;
            this.errorMessage = '';

            try {
                const response = await fetch('/api/v1/client/clients/parse-text', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({
                        text: this.parseText,
                        parse_multiple: this.parseMultiple
                    })
                });

                const data = await response.json();

                if (data.success) {
                    if (this.parseMultiple && data.clients) {
                        // 显示多选结果
                        this.multipleResults = data.clients;
                        this.showMultipleResults = true;
                        this.closeDialog();
                    } else if (data.client) {
                        // 单个当事人，直接填充
                        this.fillClientForm(data.client);
                        this.closeDialog();
                        this.showSuccess('文本解析成功，表单已自动填充');
                    }
                } else {
                    this.showError(data.error || '解析失败，请检查文本格式');
                }
            } catch (error) {
                console.error('[ClientAdminApp] 解析请求失败:', error);
                this.showError('解析请求失败，请检查网络连接');
            } finally {
                this.isParsing = false;
            }
        },

        /**
         * 选择多选结果中的一个当事人
         */
        selectClient(index) {
            const selectedClient = this.multipleResults[index];
            if (selectedClient) {
                this.fillClientForm(selectedClient);
                this.closeMultipleResultsDialog();
                this.showSuccess('已选择当事人信息并填充表单');
            }
        },

        // ========== 表单填充 ==========

        /**
         * 用解析的数据填充表单
         */
        fillClientForm(data) {
            // 填充基本字段
            this.setFieldValue('id_name', data.name);
            this.setFieldValue('id_phone', data.phone);
            this.setFieldValue('id_address', data.address);
            this.setFieldValue('id_id_number', data.id_number);
            this.setFieldValue('id_legal_representative', data.legal_representative);

            // 设置客户类型
            if (data.client_type) {
                const clientTypeField = document.getElementById('id_client_type');
                if (clientTypeField) {
                    clientTypeField.value = data.client_type;
                    // 触发 change 事件
                    clientTypeField.dispatchEvent(new Event('change'));
                }
            }

            // 高亮显示已填充的字段
            this.highlightFilledFields();
        },

        /**
         * 设置字段值
         */
        setFieldValue(fieldId, value) {
            if (value) {
                const field = document.getElementById(fieldId);
                if (field) {
                    field.value = value;
                }
            }
        },

        /**
         * 高亮显示已填充的字段
         */
        highlightFilledFields() {
            const fields = ['id_name', 'id_phone', 'id_address', 'id_id_number', 'id_legal_representative'];

            fields.forEach(fieldId => {
                const field = document.getElementById(fieldId);
                if (field && field.value) {
                    field.style.backgroundColor = '#e8f5e8';
                    field.style.borderColor = '#4caf50';

                    // 3秒后恢复正常样式
                    setTimeout(() => {
                        field.style.backgroundColor = '';
                        field.style.borderColor = '';
                    }, 3000);
                }
            });
        },

        // ========== 错误处理 ==========

        /**
         * 显示错误信息
         */
        showError(message) {
            this.errorMessage = message;
            // 5秒后自动清除
            setTimeout(() => {
                this.errorMessage = '';
            }, 5000);
        },

        /**
         * 显示成功信息
         */
        showSuccess(message) {
            this.successMessage = message;
            // 3秒后自动清除
            setTimeout(() => {
                this.successMessage = '';
            }, 3000);
        },

        // ========== 表单增强 ==========

        /**
         * 初始化表单增强功能
         */
        initFormEnhancements() {
            const clientTypeField = document.getElementById('id_client_type');
            if (clientTypeField) {
                clientTypeField.addEventListener('change', () => {
                    this.updateIdNumberLabel(clientTypeField.value);
                    this.toggleLegalRepFields(clientTypeField.value);
                });
                // 触发初始化
                this.updateIdNumberLabel(clientTypeField.value);
                this.toggleLegalRepFields(clientTypeField.value);
            }
        },

        /**
         * 更新证件号码标签
         */
        updateIdNumberLabel(clientType) {
            const label = document.querySelector('label[for="id_id_number"]');
            if (label) {
                label.textContent = clientType === 'natural' ? '身份证号码:' : '统一社会信用代码:';
            }
        },

        /**
         * 根据主体类型显示/隐藏法定代表人字段
         */
        toggleLegalRepFields(clientType) {
            const legalRepField = document.querySelector('.field-legal_representative');
            const legalRepIdField = document.querySelector('.field-legal_representative_id_number');

            if (clientType === 'natural') {
                // 自然人：隐藏法定代表人字段
                if (legalRepField) legalRepField.classList.add('hidden');
                if (legalRepIdField) legalRepIdField.classList.add('hidden');
            } else {
                // 法人/非法人组织：显示法定代表人字段
                if (legalRepField) legalRepField.classList.remove('hidden');
                if (legalRepIdField) legalRepIdField.classList.remove('hidden');
            }
        },

        /**
         * 初始化粘贴监听
         */
        initPasteListener() {
            const nameField = document.getElementById('id_name');
            if (nameField) {
                nameField.addEventListener('paste', (e) => {
                    setTimeout(() => {
                        const pastedText = nameField.value;
                        // 如果粘贴的内容包含多行或特殊格式，提示用户使用解析功能
                        if (pastedText && (pastedText.includes('\n') || pastedText.includes('：') || pastedText.includes(':'))) {
                            if (confirm('检测到您粘贴了格式化的当事人信息，是否使用自动解析功能？')) {
                                nameField.value = '';
                                this.parseText = pastedText;
                                this.openDialog();
                            }
                        }
                    }, 100);
                });
            }
        },

        // ========== 工具方法 ==========

        // ========== OA 导入 ==========

        initOAImportPreference() {
            const storageKey = 'client_oa_import_headless_mode';
            const storedValue = window.localStorage ? window.localStorage.getItem(storageKey) : null;
            const initialValue = storedValue === null ? true : storedValue !== 'false';
            this.oaHeadlessMode = initialValue;
            this.oaImportOptions.headless = initialValue;
        },

        saveOAImportPreference(headless) {
            this.oaHeadlessMode = !!headless;
            if (window.localStorage) {
                window.localStorage.setItem('client_oa_import_headless_mode', this.oaHeadlessMode ? 'true' : 'false');
            }
        },

        /**
         * 初始化 OA 导入：检查凭证并显示按钮
         */
        async initOAImport() {
            try {
                const response = await fetch('/api/v1/client/clients/check-oa-credential/', {
                    method: 'GET',
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    }
                });
                const data = await response.json();
                if (data.has_credential) {
                    const wrapper = document.getElementById('oa-import-btn-wrapper');
                    if (wrapper) {
                        wrapper.classList.remove('oa-import-hidden');
                        wrapper.classList.add('oa-import-visible');
                    }
                }
            } catch (error) {
                console.error('[ClientAdminApp] 检查OA凭证失败:', error);
            }
        },

        /**
         * 开始 OA 导入
         */
        startOAImport(triggerEvent) {
            this.openOAImportOptions(triggerEvent);
        },

        openOAImportOptions(triggerEvent) {
            this.oaImportOptions.headless = !!this.oaHeadlessMode;
            if (triggerEvent?.currentTarget?.getBoundingClientRect) {
                const rect = triggerEvent.currentTarget.getBoundingClientRect();
                this.oaImportOptions.anchorTop = Math.round(rect.bottom + 10);
                this.oaImportOptions.anchorRight = Math.max(16, Math.round(window.innerWidth - rect.right));
            }
            this.oaImportOptions.show = true;
        },

        closeOAImportOptions() {
            this.oaImportOptions.show = false;
        },

        getOAImportOptionStyle() {
            const cardWidth = 460;
            const cardHeight = 332;
            const right = Math.max(16, this.oaImportOptions.anchorRight || 24);
            const top = Math.max(16, this.oaImportOptions.anchorTop || 88);
            const maxTop = Math.max(16, window.innerHeight - cardHeight - 16);
            const clampedTop = Math.min(top, maxTop);
            const maxRight = Math.max(16, window.innerWidth - cardWidth - 16);
            const clampedRight = Math.min(right, maxRight);
            return `top:${clampedTop}px;right:${clampedRight}px;`;
        },

        async confirmOAImportOptions() {
            const headless = !!this.oaImportOptions.headless;
            let limit = null;

            if (this.oaImportOptions.importMode === 'partial') {
                const parsedLimit = Number.parseInt(String(this.oaImportOptions.limitValue), 10);
                if (!Number.isInteger(parsedLimit) || parsedLimit <= 0) {
                    this.showError('导入数量必须是大于 0 的整数');
                    return;
                }
                limit = parsedLimit;
            }

            this.saveOAImportPreference(headless);
            this.closeOAImportOptions();
            await this.beginOAImport({ headless, limit });
        },

        async beginOAImport({ headless, limit }) {
            this.oaImport.showProgress = true;
            this.oaImport.status = 'pending';
            this.oaImport.phase = 'pending';
            this.oaImport.sessionId = null;
            this.oaImport.discoveredCount = 0;
            this.oaImport.total = 0;
            this.oaImport.processed = 0;
            this.oaImport.successCount = 0;
            this.oaImport.skipCount = 0;
            this.oaImport.errorMessage = '';
            this.oaImport.progressMessage = '';

            try {
                const payload = { headless };
                if (Number.isInteger(limit) && limit > 0) {
                    payload.limit = limit;
                }
                const response = await fetch('/api/v1/client-import', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();

                if (data.error) {
                    this.oaImport.status = 'failed';
                    this.oaImport.errorMessage = data.error;
                    return;
                }

                this.oaImport.sessionId = data.id;
                this.oaImport.status = 'in_progress';
                this.pollOAImportSession();

            } catch (error) {
                console.error('[ClientAdminApp] 启动OA导入失败:', error);
                this.oaImport.status = 'failed';
                this.oaImport.errorMessage = '启动导入失败，请检查网络连接';
            }
        },

        /**
         * 轮询导入会话状态
         */
        async pollOAImportSession() {
            if (!this.oaImport.sessionId) return;

            try {
                const response = await fetch(`/api/v1/client-import/${this.oaImport.sessionId}`, {
                    method: 'GET',
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    }
                });
                const data = await response.json();

                this.oaImport.total = data.total_count || 0;
                this.oaImport.processed = (data.success_count || 0) + (data.skip_count || 0);
                this.oaImport.phase = data.phase || 'pending';
                this.oaImport.discoveredCount = data.discovered_count || 0;
                this.oaImport.successCount = data.success_count || 0;
                this.oaImport.skipCount = data.skip_count || 0;
                this.oaImport.progressMessage = data.progress_message || '';

                if (data.status === 'completed') {
                    this.oaImport.status = 'completed';
                } else if (data.status === 'failed') {
                    this.oaImport.status = 'failed';
                    this.oaImport.errorMessage = data.error_message || '导入失败';
                } else {
                    // 继续轮询（加快频率，避免阶段切换太快看不到导入进度）
                    const nextInterval = this.oaImport.phase === 'discovering' ? 800 : 1000;
                    setTimeout(() => this.pollOAImportSession(), nextInterval);
                }

            } catch (error) {
                console.error('[ClientAdminApp] 查询导入状态失败:', error);
                setTimeout(() => this.pollOAImportSession(), 5000);
            }
        },

        /**
         * 关闭 OA 导入弹窗
         */
        closeOAImport() {
            this.oaImport.showProgress = false;
            this.oaImport.status = 'idle';
        },

        getOAImportProgressPercent() {
            if (this.oaImport.total > 0) {
                return (this.oaImport.processed / this.oaImport.total) * 100;
            }
            return 0;
        },

        getOAImportProgressLabel() {
            if (this.oaImport.phase === 'discovering') {
                return `正在查找并发现当事人，已发现 ${this.oaImport.discoveredCount} 条`;
            }
            if (this.oaImport.phase === 'importing') {
                return `正在导入，已处理 ${this.oaImport.processed} / ${this.oaImport.total} 条`;
            }
            return this.oaImport.progressMessage || '正在准备导入任务...';
        },

        getOAImportSecondaryLabel() {
            if (this.oaImport.phase === 'discovering') {
                return `成功: ${this.oaImport.successCount} | 跳过: ${this.oaImport.skipCount}`;
            }
            return `已发现: ${this.oaImport.discoveredCount} | 成功: ${this.oaImport.successCount} | 跳过: ${this.oaImport.skipCount}`;
        },

        /**
         * 获取 CSRF Token
         */
        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        /**
         * 获取客户类型显示名称
         */
        getClientTypeDisplay(clientType) {
            const typeMap = {
                'natural': '自然人',
                'legal': '法人',
                'non_legal_org': '非法人组织'
            };
            return typeMap[clientType] || '自然人';
        },

        /**
         * 检查是否在添加页面
         */
        isAddPage() {
            return window.location.pathname.includes('/add/');
        }
    };
}
