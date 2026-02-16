/**
 * 诉状生成 Alpine.js 组件
 * 功能：诉状类型选择、智能推荐、文档生成下载
 *
 * Requirements: 1.3, 1.4, 2.4
 */

/**
 * 诉状生成 Alpine.js 组件
 * @param {Object} config - 配置参数
 * @param {string} config.apiBasePath - API 基础路径
 * @param {string} config.urlPattern - URL 匹配模式
 * @returns {Object} Alpine 组件对象
 */
function litigationGenerationApp(config = {}) {
    return {
        // ========== 配置参数 ==========
        apiBasePath: config.apiBasePath || '/api/v1/documents',
        urlPattern: config.urlPattern || /\/admin\/cases\/case\/(\d+)\/(change|detail)\//,

        // ========== 状态 ==========
        caseId: config.caseId || null,   // 案件 ID（可从配置传入）
        isDialogOpen: false,             // 对话框显示状态
        isGenerating: false,             // 生成中状态
        selectedType: null,              // 选中的诉状类型
        errorMessage: '',                // 错误信息
        successMessage: '',              // 成功信息

        // ========== 诉状类型定义 ==========
        litigationTypes: [
            { value: 'complaint', label: '起诉状', icon: '📄' },
            { value: 'defense', label: '答辩状', icon: '📝' },
            { value: 'counter_claim', label: '反诉状', icon: '📋', disabled: true },
            { value: 'counter_defense', label: '反诉答辩状', icon: '📑', disabled: true }
        ],

        // ========== 初始化 ==========
        init() {
            // 优先使用配置中的 caseId，否则从 URL 提取
            if (!this.caseId) {
                this.caseId = this.extractCaseId();
            }

            if (!this.caseId) {
                console.error('无法获取案件ID');
                return;
            }

            // 监听键盘事件
            this.$watch('isDialogOpen', (open) => {
                if (open) {
                    document.addEventListener('keydown', this.handleKeyDown.bind(this));
                } else {
                    document.removeEventListener('keydown', this.handleKeyDown.bind(this));
                }
            });
        },

        // ========== 工具方法 ==========

        /**
         * 从 URL 提取案件 ID
         */
        extractCaseId() {
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
         * 处理键盘事件
         */
        handleKeyDown(e) {
            if (e.key === 'Escape' && this.isDialogOpen && !this.isGenerating) {
                this.closeDialog();
            }
        },

        // ========== 计算属性 ==========

        /**
         * 获取类型的样式类
         */
        getTypeClass(type) {
            const classes = ['litigation-type-option'];

            if (type.disabled) {
                classes.push('disabled');
            } else if (this.selectedType === type.value) {
                classes.push('selected');
            }

            return classes.join(' ');
        },

        // ========== API 方法 ==========

        /**
         * 生成诉状文档
         */
        async generateDocument() {
            if (!this.selectedType || !this.caseId) {
                this.errorMessage = '请选择诉状类型';
                return;
            }

            // 检查是否为预留功能
            const type = this.litigationTypes.find(t => t.value === this.selectedType);
            if (type?.disabled) {
                this.errorMessage = '该功能正在开发中，敬请期待';
                return;
            }

            this.isGenerating = true;
            this.errorMessage = '';

            try {
                const response = await fetch(
                    `${this.apiBasePath}/cases/${this.caseId}/litigation/${this.selectedType}/download`,
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCsrfToken()
                        }
                    }
                );

                // 检查响应类型
                const contentType = response.headers.get('content-type');

                if (response.ok) {
                    if (contentType?.includes('application/json')) {
                        // JSON 响应 - 文件已保存到绑定文件夹
                        const data = await response.json();
                        this.closeDialog();
                        this.showSuccess(data.message || '诉状生成成功');
                    } else {
                        // 文件下载响应
                        const blob = await response.blob();
                        const filename = this.extractFilename(response) || this.getDefaultFilename();
                        this.downloadBlob(blob, filename);
                        this.closeDialog();
                        this.showSuccess('诉状生成成功，正在下载...');
                    }
                } else {
                    // 错误响应
                    let errorData;
                    try {
                        errorData = await response.json();
                    } catch {
                        errorData = { message: '生成失败' };
                    }
                    throw new Error(errorData.message || '诉状生成失败');
                }
            } catch (error) {
                console.error('生成诉状失败:', error);
                this.errorMessage = error.message || '诉状生成失败';
            } finally {
                this.isGenerating = false;
            }
        },

        /**
         * 从响应头提取文件名
         */
        extractFilename(response) {
            const disposition = response.headers.get('content-disposition');
            if (!disposition) return null;

            // 尝试解析 filename*=UTF-8''xxx 格式
            const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/i);
            if (utf8Match) {
                return decodeURIComponent(utf8Match[1]);
            }

            // 尝试解析 filename="xxx" 格式
            const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match) {
                return match[1].replace(/['"]/g, '');
            }

            return null;
        },

        /**
         * 获取默认文件名
         */
        getDefaultFilename() {
            const typeLabel = this.litigationTypes.find(t => t.value === this.selectedType)?.label || '诉状';
            const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
            return `${typeLabel}_${today}.docx`;
        },

        /**
         * 下载 Blob 文件
         */
        downloadBlob(blob, filename) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        },

        // ========== 对话框方法 ==========

        /**
         * 打开诉状类型选择对话框
         */
        openDialog() {
            this.selectedType = null;
            this.errorMessage = '';
            this.isDialogOpen = true;
        },

        /**
         * 关闭对话框
         */
        closeDialog() {
            if (this.isGenerating) return;
            this.isDialogOpen = false;
            this.selectedType = null;
            this.errorMessage = '';
        },

        /**
         * 点击遮罩层关闭
         */
        handleOverlayClick(e) {
            if (e.target === e.currentTarget && !this.isGenerating) {
                this.closeDialog();
            }
        },

        /**
         * 选择诉状类型
         */
        selectType(type) {
            if (type.disabled) {
                this.errorMessage = '该功能正在开发中，敬请期待';
                return;
            }
            this.selectedType = type.value;
            this.errorMessage = '';
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
        },

        /**
         * 显示错误消息
         */
        showError(message) {
            this.errorMessage = message;
        }
    };
}

// 导出到全局作用域
window.litigationGenerationApp = litigationGenerationApp;
