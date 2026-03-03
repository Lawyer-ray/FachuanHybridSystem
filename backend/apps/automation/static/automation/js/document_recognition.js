/**
 * 法院文书智能识别 - 前端交互逻辑
 *
 * 实现拖拽上传、文件识别、结果展示等功能
 * Requirements: 2.1, 2.3
 */

class DocumentRecognition {
    constructor() {
        this.dropZone = document.getElementById('drop-zone');
        this.fileInput = document.getElementById('file-input');
        this.resultSection = document.getElementById('recognition-result');
        this.errorSection = document.getElementById('error-section');
        this.loading = document.getElementById('loading');

        this.initEventListeners();
    }

    /**
     * 初始化事件监听器
     */
    initEventListeners() {
        if (!this.dropZone) {
            console.error('Drop zone element not found');
            return;
        }

        const self = this;

        // 拖拽进入
        this.dropZone.addEventListener('dragenter', function(e) {
            e.preventDefault();
            e.stopPropagation();
            self.dropZone.classList.add('drag-over');
        }, false);

        // 拖拽悬停
        this.dropZone.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            e.dataTransfer.dropEffect = 'copy';
            self.dropZone.classList.add('drag-over');
        }, false);

        // 拖拽离开
        this.dropZone.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            self.dropZone.classList.remove('drag-over');
        }, false);

        // 文件拖放处理
        this.dropZone.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            self.dropZone.classList.remove('drag-over');

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                self.uploadAndRecognize(files[0]);
            }
        }, false);

        // 文件选择变化 (label for="file-input" 会自动触发文件选择器)
        if (this.fileInput) {
            this.fileInput.addEventListener('change', function(e) {
                if (e.target.files.length > 0) {
                    self.uploadAndRecognize(e.target.files[0]);
                }
            });
        }

        // 继续识别按钮
        const recognizeAnotherBtn = document.getElementById('recognize-another');
        if (recognizeAnotherBtn) {
            recognizeAnotherBtn.addEventListener('click', function() {
                self.resetUI();
            });
        }

        // 重试按钮
        const retryBtn = document.getElementById('retry-btn');
        if (retryBtn) {
            retryBtn.addEventListener('click', function() {
                self.resetUI();
            });
        }
    }

    /**
     * 上传文件并识别
     * @param {File} file - 要上传的文件
     */
    async uploadAndRecognize(file) {
        // 验证文件类型
        const allowedTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];
        const allowedExtensions = ['.pdf', '.jpg', '.jpeg', '.png'];

        const fileExt = '.' + file.name.split('.').pop().toLowerCase();
        if (!allowedExtensions.includes(fileExt)) {
            this.showError(`不支持的文件格式: ${fileExt}，请上传 PDF 或图片文件`);
            return;
        }

        // 显示加载状态
        this.showLoading();

        // 构建表单数据
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/admin/automation/documentrecognitionproxy/recognition/upload/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            const result = await response.json();

            if (!response.ok) {
                // 处理错误响应
                const errorMsg = result.error?.message || '识别失败，请重试';
                this.showError(errorMsg);
                return;
            }

            // 显示识别结果
            this.displayResult(result);

        } catch (error) {
            console.error('Upload error:', error);
            this.showError('网络错误，请检查网络连接后重试');
        } finally {
            this.hideLoading();
        }
    }

    /**
     * 显示识别结果
     * @param {Object} result - 识别结果
     */
    displayResult(result) {
        // 隐藏错误区域
        this.errorSection.classList.add('hidden');

        // 文书类型
        const docTypeEl = document.getElementById('doc-type');
        docTypeEl.textContent = this.getDocTypeLabel(result.recognition.document_type);
        docTypeEl.className = 'result-value doc-type-' + result.recognition.document_type;

        // 案号
        const caseNumberEl = document.getElementById('case-number');
        caseNumberEl.textContent = result.recognition.case_number || '未识别';

        // 关键时间
        const keyTimeEl = document.getElementById('key-time');
        if (result.recognition.key_time) {
            const date = new Date(result.recognition.key_time);
            keyTimeEl.textContent = this.formatDateTime(date);
        } else {
            keyTimeEl.textContent = '未识别';
        }

        // 置信度
        const confidenceEl = document.getElementById('confidence');
        const confidence = result.recognition.confidence;
        confidenceEl.textContent = (confidence * 100).toFixed(1) + '%';
        confidenceEl.className = 'result-value confidence-' + this.getConfidenceLevel(confidence);

        // 提取方式
        const extractionMethodEl = document.getElementById('extraction-method');
        extractionMethodEl.textContent = this.getExtractionMethodLabel(result.recognition.extraction_method);

        // 绑定状态
        const bindingStatusEl = document.getElementById('binding-status');
        const viewCaseLink = document.getElementById('view-case-link');

        if (result.binding) {
            if (result.binding.success) {
                bindingStatusEl.textContent = `已绑定到案件：${result.binding.case_name}`;
                bindingStatusEl.className = 'result-value binding-success';

                // 显示查看案件链接
                if (result.binding.case_id) {
                    viewCaseLink.href = `/admin/cases/case/${result.binding.case_id}/change/`;
                    viewCaseLink.classList.remove('hidden');
                }
            } else {
                bindingStatusEl.textContent = result.binding.message;
                bindingStatusEl.className = 'result-value binding-warning';
                viewCaseLink.classList.add('hidden');
            }
        } else {
            bindingStatusEl.textContent = '未进行绑定';
            bindingStatusEl.className = 'result-value binding-none';
            viewCaseLink.classList.add('hidden');
        }

        // 显示结果区域
        this.resultSection.classList.remove('hidden');
        this.dropZone.classList.add('hidden');
    }

    /**
     * 获取文书类型标签
     * @param {string} type - 文书类型代码
     * @returns {string} 文书类型中文标签
     */
    getDocTypeLabel(type) {
        const labels = {
            'summons': '📄 传票',
            'execution': '📋 执行裁定书',
            'other': '❓ 其他文书'
        };
        return labels[type] || type;
    }

    /**
     * 获取提取方式标签
     * @param {string} method - 提取方式代码
     * @returns {string} 提取方式中文标签
     */
    getExtractionMethodLabel(method) {
        const labels = {
            'pdf_direct': 'PDF 直接提取',
            'ocr': 'OCR 图像识别'
        };
        return labels[method] || method;
    }

    /**
     * 获取置信度等级
     * @param {number} confidence - 置信度 (0-1)
     * @returns {string} 置信度等级
     */
    getConfidenceLevel(confidence) {
        if (confidence >= 0.8) return 'high';
        if (confidence >= 0.5) return 'medium';
        return 'low';
    }

    /**
     * 格式化日期时间
     * @param {Date} date - 日期对象
     * @returns {string} 格式化后的日期时间字符串
     */
    formatDateTime(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');

        return `${year}-${month}-${day} ${hours}:${minutes}`;
    }

    /**
     * 显示错误信息
     * @param {string} message - 错误信息
     */
    showError(message) {
        this.hideLoading();
        this.resultSection.classList.add('hidden');
        this.dropZone.classList.add('hidden');

        const errorMessageEl = document.getElementById('error-message');
        errorMessageEl.textContent = message;

        this.errorSection.classList.remove('hidden');
    }

    /**
     * 重置 UI 到初始状态
     */
    resetUI() {
        this.resultSection.classList.add('hidden');
        this.errorSection.classList.add('hidden');
        this.dropZone.classList.remove('hidden');

        // 清空文件输入
        if (this.fileInput) {
            this.fileInput.value = '';
        }
    }

    /**
     * 显示加载状态
     */
    showLoading() {
        this.loading.classList.remove('hidden');
        this.dropZone.classList.add('hidden');
        this.resultSection.classList.add('hidden');
        this.errorSection.classList.add('hidden');
    }

    /**
     * 隐藏加载状态
     */
    hideLoading() {
        this.loading.classList.add('hidden');
    }

    /**
     * 获取 CSRF Token
     * @returns {string} CSRF Token
     */
    getCsrfToken() {
        // 从隐藏的 input 获取
        const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenInput) {
            return tokenInput.value;
        }

        // 从 cookie 获取
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }

        return '';
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.docRecognition = new DocumentRecognition();
});
