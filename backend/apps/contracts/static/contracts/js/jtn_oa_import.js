/**
 * JTN OA 导入 - 金诚同达OA案件导入独立逻辑
 * 
 * 从 change_list.html 解耦，作为律所特定OA导入模块。
 * 未来换律所时，替换为对应律所的OA导入JS文件即可。
 */
function jtnOaImportApp() {
    return {
        selectedFile: null,
        isUploading: false,
        showPreview: false,
        showProgress: false,
        previewData: null,
        previewLoading: false,
        importStatus: 'pending',
        progressMessage: '',
        progressPercent: 0,
        processedCount: 0,
        totalCount: 0,
        successCount: 0,
        skipCount: 0,
        errorMessage: '',
        sessionId: null,
        pollingInterval: null,

        get selectedFileName() { return this.selectedFile?.name || ''; },
        get selectedFileSize() { return this.selectedFile?.size || 0; },
        get previewTotalCases() { return this.previewData?.total_cases || 0; },
        get previewMatched() { return this.previewData?.matched || 0; },
        get previewUnmatched() { return this.previewData?.unmatched || 0; },
        get previewList() { return this.previewData?.preview || []; },

        init() {
            this.checkOAAccess();
        },

        checkOAAccess() {
            // 根据用户账号判断是否显示OA导入按钮
        },

        onDragOver(event) {
            event.target.classList.add('dragover');
        },

        onDragLeave(event) {
            event.target.classList.remove('dragover');
        },

        onDrop(event) {
            event.target.classList.remove('dragover');
            const files = event.dataTransfer.files;
            if (files.length > 0) {
                this.selectedFile = files[0];
            }
        },

        onFileSelect(event) {
            const files = event.target.files;
            if (files.length > 0) {
                this.selectedFile = files[0];
            }
        },

        formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        },

        cancelImport() {
            this.selectedFile = null;
        },

        async startPreview() {
            if (!this.selectedFile) return;

            this.isUploading = true;

            const formData = new FormData();
            formData.append('file', this.selectedFile);

            try {
                const response = await fetch('/api/v1/case-import', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRFToken': this.getCSRFToken(),
                    },
                    credentials: 'same-origin',
                });

                const data = await response.json();

                if (data.error) {
                    alert('错误: ' + data.error);
                    return;
                }

                this.sessionId = data.id;
                this.showPreview = true;
                this.previewLoading = true;

                await this.pollPreviewResult();

            } catch (error) {
                console.error('预览失败:', error);
                alert('预览失败: ' + error.message);
            } finally {
                this.isUploading = false;
            }
        },

        async pollPreviewResult() {
            const maxAttempts = 60;
            let attempts = 0;

            const poll = async () => {
                if (attempts >= maxAttempts) {
                    this.previewLoading = false;
                    return;
                }

                try {
                    const response = await fetch(`/api/v1/case-import/${this.sessionId}`, {
                        credentials: 'same-origin',
                    });
                    const data = await response.json();

                    if (data.result_data && data.result_data.preview) {
                        this.previewLoading = false;
                        this.previewData = {
                            total_cases: data.total_count,
                            matched: data.matched_count,
                            unmatched: data.unmatched_count,
                            preview: data.result_data.preview
                        };
                    } else if (data.status === 'failed') {
                        this.previewLoading = false;
                        alert('预览失败: ' + (data.error_message || '未知错误'));
                    } else {
                        attempts++;
                        setTimeout(poll, 1000);
                    }
                } catch (error) {
                    console.error('轮询预览失败:', error);
                    attempts++;
                    setTimeout(poll, 2000);
                }
            };

            setTimeout(poll, 1000);
        },

        closePreview() {
            this.showPreview = false;
            this.previewData = null;
        },

        async startImport() {
            if (!this.previewData || this.previewData.unmatched === 0) return;

            const unmatchedCases = this.previewData.preview
                .filter(item => item.status === 'unmatched')
                .map(item => item.case_no);

            const matchedCases = this.previewData.preview
                .filter(item => item.status === 'matched')
                .map(item => item.case_no);

            this.closePreview();
            this.showProgress = true;
            this.importStatus = 'pending';

            try {
                const response = await fetch(`/api/v1/case-import/${this.sessionId}/execute`, {
                    method: 'POST',
                    body: JSON.stringify({
                        case_nos: unmatchedCases,
                        matched_case_nos: matchedCases
                    }),
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken(),
                    },
                    credentials: 'same-origin',
                });

                const data = await response.json();

                if (data.error) {
                    this.importStatus = 'failed';
                    this.errorMessage = data.error;
                    return;
                }

                this.importStatus = 'in_progress';
                this.totalCount = unmatchedCases.length;
                this.pollImportResult();

            } catch (error) {
                console.error('启动导入失败:', error);
                this.importStatus = 'failed';
                this.errorMessage = error.message;
            }
        },

        async pollImportResult() {
            const maxAttempts = 300;
            let attempts = 0;

            const poll = async () => {
                if (attempts >= maxAttempts) {
                    this.importStatus = 'failed';
                    this.errorMessage = '导入超时';
                    return;
                }

                try {
                    const response = await fetch(`/api/v1/case-import/${this.sessionId}`, {
                        credentials: 'same-origin',
                    });
                    const data = await response.json();

                    this.progressMessage = data.progress_message || '处理中...';
                    this.processedCount = (data.success_count || 0) + (data.skip_count || 0) + (data.error_count || 0);
                    this.totalCount = data.total_count || this.totalCount;
                    this.successCount = data.success_count || 0;
                    this.skipCount = data.skip_count || 0;

                    if (this.totalCount > 0) {
                        this.progressPercent = Math.round((this.processedCount / this.totalCount) * 100);
                    }

                    if (data.status === 'completed') {
                        this.importStatus = 'completed';
                        clearInterval(this.pollingInterval);
                        return;
                    }

                    if (data.status === 'failed') {
                        this.importStatus = 'failed';
                        this.errorMessage = data.error_message || '导入失败';
                        clearInterval(this.pollingInterval);
                        return;
                    }

                    attempts++;
                    setTimeout(poll, 2000);

                } catch (error) {
                    console.error('轮询导入进度失败:', error);
                    attempts++;
                    setTimeout(poll, 3000);
                }
            };

            setTimeout(poll, 2000);
        },

        closeProgress() {
            this.showProgress = false;
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
            }
        },

        goBack() {
            window.location.href = '/admin/contracts/contract/';
        },

        getCSRFToken() {
            const name = 'csrftoken';
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        }
    };
}
