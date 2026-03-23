/**
 * 财产保全材料生成组件
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
 */
function preservationMaterialsApp(config = {}) {
    return {
        apiBasePath: config.apiBasePath || '/api/v1/documents',
        caseId: config.caseId || null,
        respondentsJson: typeof config.respondentsJson === 'string' ? config.respondentsJson : '',
        respondents: [],
        hasPreservationTemplate: config.hasPreservationTemplate || false,
        hasDelayDeliveryTemplate: config.hasDelayDeliveryTemplate || false,

        isDownloading: false,
        errorMessage: '',
        successMessage: '',

        // Toast 消息队列
        toasts: [],

        get hasRespondents() {
            return Array.isArray(this.respondents) && this.respondents.length > 0;
        },

        get canDownloadPreservation() {
            return this.hasRespondents && this.hasPreservationTemplate;
        },

        get canDownloadDelayDelivery() {
            return this.hasDelayDeliveryTemplate;
        },

        get canDownloadFullPackage() {
            return this.hasRespondents;
        },

        init() {
            this.respondents = this._parseRespondents();
        },

        _parseRespondents() {
            if (!this.respondentsJson) return [];
            try {
                const parsed = JSON.parse(this.respondentsJson);
                if (Array.isArray(parsed)) return parsed;
                return [];
            } catch {
                return [];
            }
        },

        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        extractFilename(response) {
            const disposition = response.headers.get('content-disposition');
            if (!disposition) return null;

            const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/i);
            if (utf8Match) {
                return decodeURIComponent(utf8Match[1]);
            }

            const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match) {
                return match[1].replace(/['"]/g, '');
            }

            return null;
        },

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

        async fetchAndDownload(url, { defaultFilename = 'download.docx' } = {}) {
            const requestInit = {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                }
            };
            const response = await fetch(url, requestInit);

            if (!response.ok) {
                let errorData;
                try {
                    errorData = await response.json();
                } catch {
                    errorData = { message: '生成失败' };
                }
                const message = this._extractErrorMessage(errorData) || '生成失败';
                throw new Error(message);
            }

            const contentType = response.headers.get('content-type');
            if (contentType?.includes('application/json')) {
                const data = await response.json();
                return { type: 'json', data };
            }

            const blob = await response.blob();
            const filename = this.extractFilename(response) || defaultFilename;
            this.downloadBlob(blob, filename);
            return { type: 'file', filename };
        },

        _extractErrorMessage(errorData) {
            if (!errorData) return '';
            if (typeof errorData === 'string') return errorData;
            if (typeof errorData.message === 'string' && errorData.message) return errorData.message;
            if (typeof errorData.detail === 'string' && errorData.detail) return errorData.detail;
            if (Array.isArray(errorData.detail)) {
                const msgs = errorData.detail
                    .map((x) => x?.msg || x?.message || '')
                    .filter(Boolean);
                if (msgs.length) return msgs.join('；');
            }
            if (typeof errorData.error === 'string' && errorData.error) return errorData.error;
            return '';
        },

        showSuccess(message) {
            this.successMessage = message;
            setTimeout(() => {
                this.successMessage = '';
            }, 3000);
        },

        showError(message) {
            this.errorMessage = message;
            setTimeout(() => {
                this.errorMessage = '';
            }, 5000);
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

        getPreservationButtonTitle() {
            if (!this.hasRespondents) {
                return '案件没有被申请人（对方当事人）';
            }
            if (!this.hasPreservationTemplate) {
                return '案件没有绑定财产保全申请书模板';
            }
            return '下载财产保全申请书';
        },

        getDelayDeliveryButtonTitle() {
            if (!this.hasDelayDeliveryTemplate) {
                return '案件没有绑定暂缓送达申请书模板';
            }
            return '下载暂缓送达申请书';
        },

        getFullPackageButtonTitle() {
            if (!this.hasRespondents) {
                return '案件没有被申请人（对方当事人）';
            }
            return '下载全套财产保全材料';
        },

        async downloadPreservationApplication() {
            if (!this.caseId || !this.canDownloadPreservation) return;
            this.isDownloading = true;
            this.errorMessage = '';

            try {
                const result = await this.fetchAndDownload(
                    `${this.apiBasePath}/cases/${this.caseId}/preservation/application/download`,
                    { defaultFilename: '财产保全申请书.docx' }
                );
                if (result.type === 'json') {
                    this.showToast(result.data?.message || '财产保全申请书已保存', 'success');
                } else {
                    this.showToast('财产保全申请书生成成功，正在下载...', 'success');
                }
            } catch (error) {
                this.showToast(error.message || '财产保全申请书生成失败', 'error');
            } finally {
                this.isDownloading = false;
            }
        },

        async downloadDelayDeliveryApplication() {
            if (!this.caseId || !this.canDownloadDelayDelivery) return;
            this.isDownloading = true;
            this.errorMessage = '';

            try {
                const result = await this.fetchAndDownload(
                    `${this.apiBasePath}/cases/${this.caseId}/preservation/delay-delivery/download`,
                    { defaultFilename: '暂缓送达申请书.docx' }
                );
                if (result.type === 'json') {
                    this.showToast(result.data?.message || '暂缓送达申请书已保存', 'success');
                } else {
                    this.showToast('暂缓送达申请书生成成功，正在下载...', 'success');
                }
            } catch (error) {
                this.showToast(error.message || '暂缓送达申请书生成失败', 'error');
            } finally {
                this.isDownloading = false;
            }
        },

        async downloadFullPackage() {
            if (!this.caseId || !this.canDownloadFullPackage) return;
            this.isDownloading = true;
            this.errorMessage = '';

            try {
                const result = await this.fetchAndDownload(
                    `${this.apiBasePath}/cases/${this.caseId}/preservation/package/download`,
                    { defaultFilename: '全套保全材料.zip' }
                );
                if (result.type === 'json') {
                    this.showToast(result.data?.message || '全套财产保全材料已保存', 'success');
                } else {
                    this.showToast('全套财产保全材料生成成功，正在下载...', 'success');
                }
            } catch (error) {
                this.showToast(error.message || '全套财产保全材料生成失败', 'error');
            } finally {
                this.isDownloading = false;
            }
        },
    };
}

window.preservationMaterialsApp = preservationMaterialsApp;
