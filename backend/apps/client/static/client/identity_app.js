/**
 * 身份材料智能识别 Alpine.js 组件 - 核心模块
 * 功能：配置、状态、初始化、模型管理、对话框/展开管理、工具方法
 * 依赖：无（本文件必须最先加载）
 * 被依赖：identity_app_upload.js, identity_app_form.js
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 8.1, 8.2, 8.3
 */

// ========== 上传与识别模块（由 identity_app_upload.js 定义）==========
// window._identityUploadMethods

// ========== 表单填充模块（由 identity_app_form.js 定义）==========
// window._identityFormMethods

function identityApp(config = {}) {
    const base = {
        // ========== 配置 ==========
        mode: config.mode || 'dialog',      // 模式：'dialog' 或 'inline'
        instanceId: config.instanceId || 'default',  // 实例 ID，用于多实例隔离

        // ========== 状态 ==========
        isDialogOpen: false,        // 对话框显示状态（dialog 模式）
        isExpanded: false,          // 展开状态（inline 模式）
        isDragOver: false,          // 拖拽状态
        isLoading: false,           // 加载状态
        loadingText: '正在处理...', // 加载提示文本
        uploadedFile: null,         // 上传的文件
        docType: '',                // 证件类型
        recognitionResult: null,    // 识别结果
        confidence: 0,              // 置信度
        selectedModel: '',          // 选中的 LLM 模型（空表示不使用 LLM）
        models: [],                 // 可用模型列表
        errorMessage: '',           // 错误信息
        showError: false,           // 是否显示错误状态
        showResult: false,          // 是否显示结果状态
        isConfirming: false,        // 确认中状态

        // 允许的文件类型
        allowedTypes: ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'],
        // 最大文件大小 (10MB)
        maxFileSize: 10 * 1024 * 1024,

        // 字段标签映射
        fieldLabels: {
            'name': '姓名',
            'id_number': '证件号码',
            'address': '地址',
            'expiry_date': '到期日期',
            'gender': '性别',
            'ethnicity': '民族',
            'birth_date': '出生日期',
            'passport_number': '护照号码',
            'nationality': '国籍',
            'permit_number': '通行证号码',
            'household_head': '户主',
            'company_name': '公司名称',
            'credit_code': '统一社会信用代码',
            'legal_representative': '法定代表人',
            'business_scope': '经营范围',
            'registration_date': '注册日期'
        },

        // ========== 初始化 ==========
        init() {
            console.log(`身份识别 Alpine 组件已初始化 [模式: ${this.mode}, 实例: ${this.instanceId}]`);

            // dialog 模式：监听 ESC 键关闭对话框
            if (this.mode === 'dialog') {
                document.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape' && this.isDialogOpen) {
                        this.closeDialog();
                    }
                });
            }

            this.selectedModel = localStorage.getItem('client_recognize_last_model') || '';
            this.fetchModels();
        },

        // ========== 模型管理 ==========
        async fetchModels() {
            try {
                const resp = await fetch('/api/v1/llm/models');
                const data = await resp.json();
                this.models = (data.models || []).map(m => ({ id: m.id, name: m.name }));
                // 模型列表加载完成后，从 localStorage 恢复选中状态
                const saved = localStorage.getItem('client_recognize_last_model') || '';
                if (saved && this.models.some(m => m.id === saved)) {
                    this.selectedModel = saved;
                    this.$nextTick(() => {
                        const sel = this.$el.querySelector('select');
                        if (sel && sel.value !== saved) sel.value = saved;
                    });
                }
            } catch (e) {
                console.warn('加载模型列表失败:', e);
            }
        },

        saveLastModel() {
            localStorage.setItem('client_recognize_last_model', this.selectedModel);
        },

        // ========== 对话框管理（dialog 模式）==========

        /**
         * 打开识别对话框
         */
        openDialog() {
            if (this.mode !== 'dialog') return;
            this.isDialogOpen = true;
            document.body.style.overflow = 'hidden';
            this.resetState();
        },

        /**
         * 关闭识别对话框
         */
        closeDialog() {
            if (this.mode !== 'dialog') return;
            this.isDialogOpen = false;
            document.body.style.overflow = '';
            this.cleanup();
        },

        // ========== 展开/收起管理（inline 模式）==========

        /**
         * 切换展开/收起状态
         */
        toggleExpansion() {
            if (this.mode !== 'inline') return;
            this.isExpanded = !this.isExpanded;
        },

        /**
         * 重置对话框状态
         */
        resetState() {
            this.isDragOver = false;
            this.isLoading = false;
            this.loadingText = '正在处理...';
            this.uploadedFile = null;
            this.docType = '';
            this.recognitionResult = null;
            this.confidence = 0;
            this.selectedModel = localStorage.getItem('client_recognize_last_model') || '';
            this.errorMessage = '';
            this.showError = false;
            this.showResult = false;
            this.isConfirming = false;
        },

        /**
         * 清理内部状态
         */
        cleanup() {
            this.recognitionResult = null;
            this.uploadedFile = null;
        },

        /**
         * 重置识别状态（inline 模式使用）
         */
        resetRecognition() {
            this.resetState();
        },

        // ========== 状态显示 ==========

        /**
         * 显示加载状态
         * @param {string} text - 加载提示文本
         */
        showLoading(text = '正在处理...') {
            this.isLoading = true;
            this.loadingText = text;
            this.showError = false;
            this.showResult = false;
        },

        /**
         * 显示识别结果
         * @param {Object} result - 识别结果
         */
        displayResult(result) {
            this.recognitionResult = result;
            this.confidence = Math.round((result.confidence || 0) * 100);
            this.isLoading = false;
            this.showError = false;
            this.showResult = true;
        },

        /**
         * 显示错误状态
         * @param {string} message - 错误信息
         */
        displayError(message) {
            this.errorMessage = message;
            this.isLoading = false;
            this.showResult = false;
            this.showError = true;
        },

        // ========== 工具方法 ==========

        /**
         * 获取CSRF Token
         * @returns {string} - CSRF Token
         */
        getCsrfToken() {
            if (window.FachuanCSRF && window.FachuanCSRF.getToken) return window.FachuanCSRF.getToken() || '';
            // 从隐藏的input获取
            const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
            if (tokenInput) {
                return tokenInput.value;
            }

            // 从cookie获取
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'csrftoken') {
                    return value;
                }
            }

            return '';
        },

        /**
         * 是否显示上传区域
         * @returns {boolean}
         */
        showUploadZone() {
            return !this.isLoading && !this.showError && !this.showResult;
        }
    };

    // 合并上传模块和表单模块的方法
    return Object.assign(base,
        window._identityUploadMethods || {},
        window._identityFormMethods || {}
    );
}
