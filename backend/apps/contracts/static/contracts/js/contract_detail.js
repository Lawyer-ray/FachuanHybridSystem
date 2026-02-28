/**
 * 合同详情页 Alpine.js 组件
 *
 * 功能包括：
 * - 标签页切换逻辑
 * - 标签页状态持久化（localStorage）
 * - 文档生成方法（合同、补充协议、文件夹）
 * - Toast 消息提示
 *
 * Requirements: 3.6, 3.7
 */

/**
 * 合同详情页 Alpine.js 应用
 * @param {Object} config - 配置对象
 * @param {number} config.contractId - 合同ID
 * @returns {Object} Alpine.js 组件数据对象
 */
function contractDetailApp(config = {}) {
    const contractId = config.contractId;
    const storageKey = 'contractDetailTab';

    return {
        // 当前激活的标签页
        activeTab: localStorage.getItem(storageKey) || 'basic',

        // 文档生成状态
        generating: false,
        generatingType: null,

        // 补充协议选择对话框
        showAgreementDialog: false,
        selectedAgreementId: null,

        // 占位符预览
        showPreviewDialog: false,
        showAgreementPreviewSelect: false,
        previewAgreementId: null,
        previewTitle: '',
        previewRows: [],
        isLoadingPreview: false,

        // Toast 消息队列
        toasts: [],

        /**
         * 组件初始化
         * 监听标签页切换并持久化到 localStorage
         */
        init() {
            this.$watch('activeTab', (value) => {
                localStorage.setItem(storageKey, value);
            });
        },

        /**
         * 显示 Toast 消息
         * @param {string} message - 消息内容
         * @param {string} type - 消息类型 ('success' | 'error')
         */
        showToast(message, type = 'success') {
            const toast = { message, type, show: true };
            this.toasts.push(toast);

            // 3秒后自动隐藏
            setTimeout(() => {
                toast.show = false;
                // 动画结束后移除
                setTimeout(() => {
                    const index = this.toasts.indexOf(toast);
                    if (index > -1) {
                        this.toasts.splice(index, 1);
                    }
                }, 300);
            }, 3000);
        },

        /**
         * 获取 CSRF Token
         * @returns {string} CSRF Token
         */
        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        /**
         * 处理文件下载响应
         * @param {Response} response - fetch 响应对象
         * @param {string} defaultFilename - 默认文件名
         */
        async handleDownloadResponse(response, defaultFilename) {
            const blob = await response.blob();
            const contentDisposition = response.headers.get('content-disposition');
            let filename = defaultFilename;

            if (contentDisposition) {
                // 尝试解析 UTF-8 编码的文件名
                const match = contentDisposition.match(/filename\*=UTF-8''(.+)/);
                if (match) {
                    filename = decodeURIComponent(match[1]);
                } else {
                    // 尝试解析普通文件名
                    const simpleMatch = contentDisposition.match(/filename="?([^";\n]+)"?/);
                    if (simpleMatch) {
                        filename = simpleMatch[1];
                    }
                }
            }

            // 创建下载链接
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            return filename;
        },

        /**
         * 生成合同文档
         * 调用 API: /api/v1/documents/contracts/{id}/download
         */
        async generateContract() {
            if (this.generating || !contractId) return;

            this.generating = true;
            this.generatingType = 'contract';

            try {
                const response = await fetch(`/api/v1/documents/contracts/${contractId}/download`);

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.message || errorData.detail || '生成失败');
                }

                const contentType = response.headers.get('content-type');

                if (contentType && contentType.includes('application/json')) {
                    // 文件已保存到绑定文件夹
                    const data = await response.json();
                    this.showToast(data.message || '合同已生成并保存', 'success');
                } else {
                    // 下载文件
                    await this.handleDownloadResponse(response, '合同.docx');
                    this.showToast('合同生成成功，已开始下载', 'success');
                }
            } catch (error) {
                console.error('生成合同失败:', error);
                this.showToast(error.message || '生成合同失败', 'error');
            } finally {
                this.generating = false;
                this.generatingType = null;
            }
        },

        /**
         * 生成补充协议文档
         * 调用 API: /api/v1/documents/contracts/{id}/supplementary-agreements/{agreementId}/download
         */
        async generateSupplementaryAgreement() {
            if (this.generating || !this.selectedAgreementId || !contractId) return;

            this.generating = true;
            this.generatingType = 'agreement';
            this.showAgreementDialog = false;

            try {
                const response = await fetch(
                    `/api/v1/documents/contracts/${contractId}/supplementary-agreements/${this.selectedAgreementId}/download`
                );

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.message || errorData.detail || '生成失败');
                }

                const contentType = response.headers.get('content-type');

                if (contentType && contentType.includes('application/json')) {
                    // 文件已保存到绑定文件夹
                    const data = await response.json();
                    this.showToast(data.message || '补充协议已生成并保存', 'success');
                } else {
                    // 下载文件
                    await this.handleDownloadResponse(response, '补充协议.docx');
                    this.showToast('补充协议生成成功，已开始下载', 'success');
                }
            } catch (error) {
                console.error('生成补充协议失败:', error);
                this.showToast(error.message || '生成补充协议失败', 'error');
            } finally {
                this.generating = false;
                this.generatingType = null;
                this.selectedAgreementId = null;
            }
        },

        /**
         * 生成文件夹（ZIP 压缩包）
         * 调用 API: /api/v1/documents/contracts/{id}/folder/download
         */
        async generateFolder() {
            if (this.generating || !contractId) return;

            this.generating = true;
            this.generatingType = 'folder';

            try {
                const response = await fetch(`/api/v1/documents/contracts/${contractId}/folder/download`);

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.message || errorData.detail || '生成失败');
                }

                // 文件夹总是返回 ZIP 下载
                await this.handleDownloadResponse(response, '文件夹.zip');
                this.showToast('文件夹生成成功，已开始下载', 'success');
            } catch (error) {
                console.error('生成文件夹失败:', error);
                this.showToast(error.message || '生成文件夹失败', 'error');
            } finally {
                this.generating = false;
                this.generatingType = null;
            }
        },

        /**
         * 打开补充协议选择对话框
         */
        openAgreementDialog() {
            this.selectedAgreementId = null;
            this.showAgreementDialog = true;
        },

        /**
         * 关闭补充协议选择对话框
         */
        closeAgreementDialog() {
            this.showAgreementDialog = false;
            this.selectedAgreementId = null;
        },

        /**
         * 选择补充协议
         * @param {number} agreementId - 补充协议ID
         */
        selectAgreement(agreementId) {
            this.selectedAgreementId = agreementId;
        },

        async previewContract() {
            this.previewTitle = '合同替换词预览';
            this.previewRows = [];
            this.isLoadingPreview = true;
            this.showPreviewDialog = true;
            try {
                const resp = await fetch(`/api/v1/documents/contracts/${contractId}/preview`);
                const data = await resp.json();
                this.previewRows = data.data || [];
            } catch (e) {
                this.showToast('预览加载失败', 'error');
            } finally {
                this.isLoadingPreview = false;
            }
        },

        openAgreementPreviewDialog() {
            this.previewAgreementId = null;
            this.showAgreementPreviewSelect = true;
        },

        async previewAgreement() {
            if (!this.previewAgreementId) return;
            this.showAgreementPreviewSelect = false;
            this.previewTitle = '补充协议替换词预览';
            this.previewRows = [];
            this.isLoadingPreview = true;
            this.showPreviewDialog = true;
            try {
                const resp = await fetch(`/api/v1/documents/contracts/${contractId}/supplementary-agreements/${this.previewAgreementId}/preview`);
                const data = await resp.json();
                this.previewRows = data.data || [];
            } catch (e) {
                this.showToast('预览加载失败', 'error');
            } finally {
                this.isLoadingPreview = false;
            }
        }
    };
}

// 导出到全局作用域
window.contractDetailApp = contractDetailApp;
