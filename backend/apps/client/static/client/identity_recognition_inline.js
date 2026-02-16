/**
 * @deprecated 此文件已废弃，请使用 identity_app.js (Alpine.js 组件) 替代
 * 新组件位置: backend/apps/client/static/client/identity_app.js
 * 新组件支持 inline 模式：identityApp({ mode: 'inline' })
 * 迁移日期: 2026-01-08
 * 保留此文件仅供参考和回滚使用
 *
 * 身份材料智能识别 - 内联版本
 * 优雅的内联设计，无需弹窗
 */

class IdentityRecognitionInline {
    constructor() {
        this.recognitionResult = null;
        this.uploadedFile = null;
        this.isExpanded = false;  // 默认收起状态

        this.initElements();
        this.initEventListeners();
    }

    /**
     * 初始化DOM元素引用
     */
    initElements() {
        // 主要容器
        this.container = document.querySelector('.identity-recognition-inline');
        this.header = document.querySelector('.recognition-header');
        this.content = document.getElementById('identityRecognitionContent');
        this.toggleBtn = document.getElementById('toggleIdentityRecognition');
        this.toggleText = this.toggleBtn?.querySelector('.toggle-text');
        this.toggleIcon = this.toggleBtn?.querySelector('.toggle-icon');

        // 表单元素
        this.docTypeSelect = document.getElementById('identityDocType');
        this.uploadZone = document.getElementById('identityUploadZone');
        this.fileInput = document.getElementById('identityFileInput');

        // 状态区域
        this.processingState = document.getElementById('identityProcessingState');
        this.processingText = document.getElementById('processingText');
        this.resultSection = document.getElementById('identityResultSection');
        this.errorSection = document.getElementById('identityErrorSection');

        // 结果显示
        this.confidenceScore = document.getElementById('confidenceScore');
        this.resultGrid = document.getElementById('identityResultGrid');
        this.applyBtn = document.getElementById('applyResultBtn');
        this.resetBtn = document.getElementById('resetRecognitionBtn');
        this.retryBtn = document.getElementById('retryRecognitionBtn');
        this.errorMessage = document.getElementById('errorMessage');
    }

    /**
     * 初始化事件监听器
     */
    initEventListeners() {
        if (!this.container) {
            console.warn('Identity recognition inline container not found');
            return;
        }

        // 切换展开/收起
        this.header?.addEventListener('click', () => this.toggleExpansion());

        // 上传区域事件
        if (this.uploadZone && this.fileInput) {
            this.uploadZone.addEventListener('click', () => this.fileInput.click());
            this.uploadZone.addEventListener('dragenter', this.handleDragEnter.bind(this));
            this.uploadZone.addEventListener('dragover', this.handleDragOver.bind(this));
            this.uploadZone.addEventListener('dragleave', this.handleDragLeave.bind(this));
            this.uploadZone.addEventListener('drop', this.handleDrop.bind(this));

            this.fileInput.addEventListener('change', this.handleFileSelect.bind(this));
        }

        // 按钮事件
        this.applyBtn?.addEventListener('click', () => this.applyResult());
        this.resetBtn?.addEventListener('click', () => this.resetRecognition());
        this.retryBtn?.addEventListener('click', () => this.resetRecognition());
    }

    /**
     * 切换展开/收起状态
     */
    toggleExpansion() {
        this.isExpanded = !this.isExpanded;

        if (this.isExpanded) {
            this.content?.classList.remove('collapsed');
            this.content?.classList.add('expanded');
            this.toggleIcon?.classList.add('expanded');
        } else {
            this.content?.classList.remove('expanded');
            this.content?.classList.add('collapsed');
            this.toggleIcon?.classList.remove('expanded');
        }
    }

    /**
     * 拖拽事件处理
     */
    handleDragEnter(e) {
        e.preventDefault();
        e.stopPropagation();
        this.uploadZone?.classList.add('drag-over');
    }

    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'copy';
    }

    handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();

        if (!this.uploadZone?.contains(e.relatedTarget)) {
            this.uploadZone?.classList.remove('drag-over');
        }
    }

    handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this.uploadZone?.classList.remove('drag-over');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            this.processFile(files[0]);
        }
    }

    /**
     * 文件选择处理
     */
    handleFileSelect(e) {
        if (e.target.files.length > 0) {
            this.processFile(e.target.files[0]);
        }
    }

    /**
     * 处理上传的文件
     */
    async processFile(file) {
        try {
            // 验证文件
            this.validateFile(file);

            // 检查证件类型
            const docType = this.docTypeSelect?.value;
            if (!docType) {
                throw new Error('请先选择证件类型');
            }

            this.uploadedFile = file;
            // 同步到全局变量，供内联脚本使用
            window._identityUploadedFile = file;

            // 显示处理状态
            this.showProcessing('正在识别证件信息...');

            // 调用识别API
            const result = await this.recognizeIdentity(file, docType);

            // 显示结果
            this.showResult(result);

        } catch (error) {
            console.error('处理文件失败:', error);
            this.showError(error.message);
        }
    }

    /**
     * 验证文件类型和大小
     */
    validateFile(file) {
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
        const maxSize = 10 * 1024 * 1024; // 10MB

        if (!allowedTypes.includes(file.type)) {
            throw new Error('不支持的文件格式，请上传 JPG、PNG 或 PDF 文件');
        }

        if (file.size > maxSize) {
            throw new Error('文件大小不能超过 10MB');
        }
    }

    /**
     * 调用身份识别API
     */
    async recognizeIdentity(file, docType) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('doc_type', docType);

        const response = await fetch('/api/v1/client/identity-doc/recognize', {
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

    /**
     * 显示处理状态
     */
    showProcessing(text = '正在处理...') {
        this.hideAllStates();

        if (this.processingText) {
            this.processingText.textContent = text;
        }

        this.processingState?.classList.remove('hidden');
    }

    /**
     * 显示识别结果
     */
    showResult(result) {
        this.recognitionResult = result;
        this.hideAllStates();

        // 更新置信度
        this.updateConfidenceScore(result.confidence);

        // 渲染结果字段
        this.renderResultFields(result.extracted_data);

        this.resultSection?.classList.remove('hidden');
    }

    /**
     * 更新置信度显示
     */
    updateConfidenceScore(confidence) {
        if (!this.confidenceScore) return;

        const percentage = Math.round((confidence || 0) * 100);
        this.confidenceScore.textContent = `置信度: ${percentage}%`;

        // 设置样式类
        this.confidenceScore.className = `confidence-score ${this.getConfidenceClass(percentage)}`;
    }

    /**
     * 获取置信度样式类
     */
    getConfidenceClass(percentage) {
        if (percentage >= 80) return 'high';
        if (percentage >= 60) return 'medium';
        return 'low';
    }

    /**
     * 渲染识别结果字段
     */
    renderResultFields(extractedData) {
        if (!this.resultGrid || !extractedData) return;

        this.resultGrid.innerHTML = '';

        // 遍历提取的数据
        Object.entries(extractedData).forEach(([key, value]) => {
            if (value && value.toString().trim()) {
                const fieldDiv = document.createElement('div');
                fieldDiv.className = 'result-field';
                fieldDiv.innerHTML = `
                    <label>${this.getFieldLabel(key)}</label>
                    <span class="field-value" data-field="${key}">${this.formatFieldValue(key, value)}</span>
                `;
                this.resultGrid.appendChild(fieldDiv);
            }
        });

        // 如果没有有效数据，显示提示
        if (this.resultGrid.children.length === 0) {
            this.resultGrid.innerHTML = '<div class="text-center" style="color: #999; padding: 20px;">未识别到有效信息</div>';
        }
    }

    /**
     * 获取字段标签
     */
    getFieldLabel(key) {
        const labels = {
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
        };
        return labels[key] || key;
    }

    /**
     * 格式化字段值
     */
    formatFieldValue(key, value) {
        // 日期字段格式化
        if (key.includes('date') && value) {
            try {
                const date = new Date(value);
                if (!isNaN(date.getTime())) {
                    return date.toLocaleDateString('zh-CN');
                }
            } catch (e) {
                // 如果不是有效日期，返回原值
            }
        }

        return value;
    }

    /**
     * 显示错误状态
     */
    showError(message) {
        this.hideAllStates();

        if (this.errorMessage) {
            this.errorMessage.textContent = message;
        }

        this.errorSection?.classList.remove('hidden');
    }

    /**
     * 隐藏所有状态区域
     */
    hideAllStates() {
        const states = [this.processingState, this.resultSection, this.errorSection];
        states.forEach(state => state?.classList.add('hidden'));
    }

    /**
     * 应用识别结果到表单
     */
    async applyResult() {
        if (!this.recognitionResult || !this.uploadedFile) {
            this.showError('没有可应用的识别结果');
            return;
        }

        console.log('应用识别结果:', this.recognitionResult);

        const originalText = this.applyBtn?.textContent || '';

        try {
            // 禁用按钮
            this.setButtonState(this.applyBtn, true, '应用中...');

            // 填充表单
            this.fillClientForm(this.recognitionResult.extracted_data);

            // 如果当事人已保存，创建证件记录
            const clientId = this.getClientId();
            if (clientId) {
                await this.createIdentityDocRecord(clientId);
            }

            // 显示成功消息
            this.showSuccessMessage('识别结果已成功应用到表单');

            // 不自动收起，让用户看到成功消息

        } catch (error) {
            console.error('应用识别结果失败:', error);
            this.showError('应用识别结果失败: ' + error.message);
        } finally {
            // 恢复按钮状态
            this.setButtonState(this.applyBtn, false, originalText);
        }
    }

    /**
     * 设置按钮状态
     */
    setButtonState(button, disabled, text) {
        if (!button) return;

        button.disabled = disabled;
        if (text) {
            button.textContent = text;
        }
    }

    /**
     * 填充客户表单
     */
    fillClientForm(extractedData) {
        if (!extractedData) return;

        console.log('填充表单数据:', extractedData);

        // 根据证件类型推断当事人类型
        const docType = this.docTypeSelect?.value;

        // 特殊处理：法定代表人/负责人身份证
        // 只填充 legal_representative_id_number 字段，不修改其他字段
        if (docType === 'legal_rep_id_card') {
            console.log('法定代表人/负责人身份证模式：只填充身份证号码');

            // 只填充法定代表人/负责人身份证号码
            const idNumber = extractedData.id_number || extractedData.id_card_number || '';
            if (idNumber) {
                this.setFieldValue('legal_representative_id_number', idNumber);
            }

            // 高亮填充的字段
            const field = document.getElementById('id_legal_representative_id_number');
            if (field && field.value) {
                field.style.backgroundColor = '#e8f5e8';
                field.style.borderColor = '#4caf50';
                field.style.transition = 'all 0.3s ease';
                setTimeout(() => {
                    field.style.backgroundColor = '';
                    field.style.borderColor = '';
                }, 3000);
            }

            return;
        }

        if (docType === 'business_license') {
            // 营业执照 -> 法人
            this.setFieldValue('client_type', 'legal');
            if (extractedData.company_name) {
                this.setFieldValue('name', extractedData.company_name);
            }
            if (extractedData.credit_code) {
                this.setFieldValue('id_number', extractedData.credit_code);
            }
            if (extractedData.legal_representative) {
                this.setFieldValue('legal_representative', extractedData.legal_representative);
            }
            if (extractedData.address) {
                this.setFieldValue('address', extractedData.address);
            }
        } else {
            // 其他证件 -> 自然人
            this.setFieldValue('client_type', 'natural');

            // 姓名
            if (extractedData.name) {
                this.setFieldValue('name', extractedData.name);
            }

            // 证件号码 - 支持多种字段名
            const idNumber = extractedData.id_number || extractedData.id_card_number ||
                           extractedData.passport_number || extractedData.permit_number;
            if (idNumber) {
                this.setFieldValue('id_number', idNumber);
            }

            // 地址
            if (extractedData.address) {
                this.setFieldValue('address', extractedData.address);
            }
        }

        // 触发客户类型变更事件，更新表单显示
        const clientTypeField = document.getElementById('id_client_type');
        if (clientTypeField) {
            clientTypeField.dispatchEvent(new Event('change'));
        }

        // 高亮填充的字段
        this.highlightFilledFields();
    }

    /**
     * 设置表单字段值
     */
    setFieldValue(fieldName, value) {
        const field = document.getElementById('id_' + fieldName);
        console.log(`设置字段 ${fieldName}:`, value, '元素:', field);

        if (field && value !== undefined && value !== null && value !== '') {
            if (field.type === 'checkbox') {
                field.checked = !!value;
            } else if (field.tagName === 'SELECT') {
                // 下拉框
                field.value = value;
            } else {
                // 文本输入框
                field.value = value;
            }
            // 触发 change 和 input 事件
            field.dispatchEvent(new Event('change', { bubbles: true }));
            field.dispatchEvent(new Event('input', { bubbles: true }));
            return true;
        }
        return false;
    }

    /**
     * 高亮填充的字段
     */
    highlightFilledFields() {
        const fieldNames = ['name', 'id_number', 'address', 'legal_representative'];

        fieldNames.forEach(fieldName => {
            const field = document.getElementById('id_' + fieldName);
            if (field && field.value) {
                field.style.backgroundColor = '#e8f5e8';
                field.style.borderColor = '#4caf50';
                field.style.transition = 'all 0.3s ease';

                // 3秒后恢复原样
                setTimeout(() => {
                    field.style.backgroundColor = '';
                    field.style.borderColor = '';
                }, 3000);
            }
        });
    }

    /**
     * 获取当前当事人ID（如果已保存）
     */
    getClientId() {
        const url = window.location.pathname;
        const match = url.match(/\/admin\/client\/client\/(\d+)\/change\//);
        return match ? match[1] : null;
    }

    /**
     * 创建证件记录
     */
    async createIdentityDocRecord(clientId) {
        const formData = new FormData();
        formData.append('client', clientId);
        formData.append('doc_type', this.docTypeSelect?.value || '');
        formData.append('file', this.uploadedFile);

        // 添加识别到的到期日期
        if (this.recognitionResult.extracted_data.expiry_date) {
            formData.append('expiry_date', this.recognitionResult.extracted_data.expiry_date);
        }

        const response = await fetch('/api/v1/client/identity-docs/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': this.getCsrfToken()
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '创建证件记录失败');
        }

        return await response.json();
    }

    /**
     * 重置识别状态
     */
    resetRecognition() {
        this.hideAllStates();

        // 重置表单
        if (this.docTypeSelect) {
            this.docTypeSelect.value = '';
        }
        if (this.fileInput) {
            this.fileInput.value = '';
        }

        // 清理状态
        this.recognitionResult = null;
        this.uploadedFile = null;
    }

    /**
     * 显示成功消息
     */
    showSuccessMessage(message) {
        // 创建临时成功提示
        const successDiv = document.createElement('div');
        successDiv.className = 'success-message';
        successDiv.style.cssText = `
            background: #d4edda;
            color: #155724;
            padding: 12px 16px;
            border: 1px solid #c3e6cb;
            border-radius: 8px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        `;
        successDiv.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M9,20.42L2.79,14.21L5.62,11.38L9,14.77L18.88,4.88L21.71,7.71L9,20.42Z"/>
            </svg>
            ${message}
        `;

        // 插入到内容区域顶部
        const content = this.content;
        if (content) {
            content.insertBefore(successDiv, content.firstChild);

            // 3秒后移除
            setTimeout(() => {
                if (successDiv.parentNode) {
                    successDiv.parentNode.removeChild(successDiv);
                }
            }, 3000);
        }
    }

    /**
     * 获取CSRF Token
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
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 延迟初始化，确保DOM完全加载
    setTimeout(() => {
        new IdentityRecognitionInline();
    }, 100);
});

// 导出类供其他模块使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = IdentityRecognitionInline;
}
