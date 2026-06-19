/**
 * 身份材料智能识别 Alpine.js 组件 - 文件上传与识别模块
 * 功能：拖拽事件处理、文件验证、文件处理、OCR 识别调用
 * 依赖：identity_app.js（必须先加载）
 * 被依赖：identity_app_form.js
 */

window._identityUploadMethods = {
    // ========== 拖拽事件处理 ==========

    /**
     * 拖拽进入处理
     */
    handleDragEnter(e) {
        e.preventDefault();
        e.stopPropagation();
        this.isDragOver = true;
    },

    /**
     * 拖拽悬停处理
     */
    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'copy';
    },

    /**
     * 拖拽离开处理
     */
    handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();

        // 只有当鼠标真正离开上传区域时才移除样式
        const uploadZone = e.currentTarget;
        if (!uploadZone.contains(e.relatedTarget)) {
            this.isDragOver = false;
        }
    },

    /**
     * 文件拖放处理
     */
    handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this.isDragOver = false;

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            this.processFile(files[0]);
        }
    },

    /**
     * 文件选择处理
     */
    handleFileSelect(e) {
        if (e.target.files.length > 0) {
            this.processFile(e.target.files[0]);
        }
    },

    // ========== 文件验证 ==========

    /**
     * 验证文件类型和大小
     * @param {File} file - 要验证的文件
     * @returns {Object} - { valid: boolean, error: string }
     */
    validateFile(file) {
        if (!this.allowedTypes.includes(file.type)) {
            return {
                valid: false,
                error: '不支持的文件格式，请上传 JPG、PNG 或 PDF 文件'
            };
        }

        if (file.size > this.maxFileSize) {
            return {
                valid: false,
                error: '文件大小不能超过 10MB'
            };
        }

        return { valid: true, error: '' };
    },

    // ========== 文件处理 ==========

    /**
     * 处理上传的文件
     * @param {File} file - 上传的文件
     */
    async processFile(file) {
        try {
            // 验证文件
            const validation = this.validateFile(file);
            if (!validation.valid) {
                this.displayError(validation.error);
                return;
            }

            // 检查证件类型
            if (!this.docType) {
                this.displayError('请先选择证件类型');
                return;
            }

            this.uploadedFile = file;

            // 显示加载状态
            this.showLoading('正在上传文件...');

            // 调用识别API
            const result = await this.recognizeIdentity(file, this.docType);

            // 显示结果
            this.displayResult(result);

        } catch (error) {
            console.error('处理文件失败:', error);
            this.displayError(error.message);
        }
    },

    // ========== OCR 识别 ==========

    /**
     * 调用身份识别API
     * @param {File} file - 要识别的文件
     * @param {string} docType - 证件类型
     * @returns {Object} - 识别结果
     */
    async recognizeIdentity(file, docType) {
        const formData = new FormData();
        formData.append('file', file);
        let url = '/api/v1/client/identity-doc/recognize?doc_type=' + encodeURIComponent(docType);
        const sel = this.$el.querySelector('select[x-model="selectedModel"]');
        const domModel = sel ? sel.value : this.selectedModel;
        if (domModel) {
            url += '&model=' + encodeURIComponent(domModel);
        }

        this.loadingText = '正在识别证件...';

        const response = await fetch(url, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': this.getCsrfToken()
            }
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || `HTTP ${response.status}: 识别请求失败`);
        }

        if (!result.success) {
            throw new Error(result.error || '识别失败');
        }

        return result;
    }
};
