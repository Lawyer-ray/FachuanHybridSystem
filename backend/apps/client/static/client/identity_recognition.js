/**
 * @deprecated 此文件已废弃，请使用 identity_app.js (Alpine.js 组件) 替代
 * 新组件位置: backend/apps/client/static/client/identity_app.js
 * 迁移日期: 2026-01-08
 * 保留此文件仅供参考和回滚使用
 *
 * 身份材料智能识别 - JavaScript 逻辑 (原生 JS 版本)
 * 实现文件上传、API 调用、结果显示和表单填充
 * Requirements: 4.5, 4.6, 4.7, 4.11
 */

class IdentityRecognition {
    constructor() {
        this.dialog = null;
        this.uploadZone = null;
        this.fileInput = null;
        this.docTypeSelect = null;
        this.recognitionResult = null;
        this.uploadedFile = null;

        this.initElements();
        this.initEventListeners();
    }

    /**
     * 初始化DOM元素引用
     */
    initElements() {
        this.dialog = document.getElementById('identityRecognitionDialog');
        this.uploadZone = document.getElementById('identityUploadZone');
        this.fileInput = document.getElementById('identityFileInput');
        this.docTypeSelect = document.getElementById('identityDocType');

        // 状态区域
        this.loadingState = document.getElementById('identityLoadingState');
        this.resultCard = document.getElementById('identityResultCard');
        this.errorState = document.getElementById('identityErrorState');

        // 结果显示元素
        this.confidenceTag = document.getElementById('identityConfidenceTag');
        this.resultGrid = document.getElementById('identityResultGrid');
        this.confirmBtn = document.getElementById('confirmIdentityBtn');

        // 文本元素
        this.loadingText = document.getElementById('identityLoadingText');
        this.errorMessage = document.getElementById('identityErrorMessage');
    }

    /**
     * 初始化事件监听器
     */
    initEventListeners() {
        if (!this.uploadZone || !this.fileInput) {
            console.warn('Identity recognition elements not found');
            return;
        }

        // 拖拽事件
        this.uploadZone.addEventListener('dragenter', this.handleDragEnter.bind(this));
        this.uploadZone.addEventListener('dragover', this.handleDragOver.bind(this));
        this.uploadZone.addEventListener('dragleave', this.handleDragLeave.bind(this));
        this.uploadZone.addEventListener('drop', this.handleDrop.bind(this));

        // 文件选择事件
        this.fileInput.addEventListener('change', this.handleFileSelect.bind(this));

        // 对话框关闭事件（点击遮罩层）
        if (this.dialog) {
            this.dialog.addEventListener('click', (e) => {
                if (e.target.classList.contains('dialog-overlay')) {
                    this.closeDialog();
                }
            });
        }

        // ESC键关闭对话框
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.dialog && !this.dialog.classList.contains('hidden')) {
                this.closeDialog();
            }
        });
    }

    /**
     * 拖拽进入处理
     */
    handleDragEnter(e) {
        e.preventDefault();
        e.stopPropagation();
        this.uploadZone.classList.add('drag-over');
    }

    /**
     * 拖拽悬停处理
     */
    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'copy';
    }

    /**
     * 拖拽离开处理
     */
    handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();

        // 只有当鼠标真正离开上传区域时才移除样式
        if (!this.uploadZone.contains(e.relatedTarget)) {
            this.uploadZone.classList.remove('drag-over');
        }
    }

    /**
     * 文件拖放处理
     */
    handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this.uploadZone.classList.remove('drag-over');

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
     * 打开识别对话框
     */
    openDialog() {
        if (!this.dialog) return;

        this.dialog.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        this.resetDialog();
    }

    /**
     * 关闭识别对话框
     */
    closeDialog() {
        if (!this.dialog) return;

        this.dialog.classList.add('hidden');
        document.body.style.overflow = '';
        this.cleanup();
    }

    /**
     * 重置对话框到初始状态
     */
    resetDialog() {
        // 隐藏所有状态区域
        this.hideAllStates();

        // 显示上传区域
        if (this.uploadZone) {
            this.uploadZone.classList.remove('hidden');
        }

        // 重置表单
        if (this.docTypeSelect) {
            this.docTypeSelect.value = '';
        }
        if (this.fileInput) {
            this.fileInput.value = '';
        }

        // 清理状态
        this.cleanup();
    }

    /**
     * 隐藏所有状态区域
     */
    hideAllStates() {
        const states = [this.loadingState, this.resultCard, this.errorState];
        states.forEach(state => {
            if (state) state.classList.add('hidden');
        });
    }

    /**
     * 清理内部状态
     */
    cleanup() {
        this.recognitionResult = null;
        this.uploadedFile = null;
    }

    /**
     * 处理上传的文件
     */
    async processFile(file) {
        try {
            // 验证文件
            this.validateFile(file);

            // 检查证件类型
            const docType = this.docTypeSelect ? this.docTypeSelect.value : '';
            if (!docType) {
                throw new Error('请先选择证件类型');
            }

            this.uploadedFile = file;

            // 显示加载状态
            this.showLoading('正在上传文件...');

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
     * 显示加载状态
     */
    showLoading(text = '正在处理...') {
        this.hideAllStates();

        if (this.uploadZone) {
            this.uploadZone.classList.add('hidden');
        }

        if (this.loadingText) {
            this.loadingText.textContent = text;
        }

        if (this.loadingState) {
            this.loadingState.classList.remove('hidden');
        }
    }

    /**
     * 显示识别结果
     */
    showResult(result) {
        this.recognitionResult = result;
        this.hideAllStates();

        if (this.uploadZone) {
            this.uploadZone.classList.add('hidden');
        }

        // 更新置信度标签
        this.updateConfidenceTag(result.confidence);

        // 生成结果字段
        this.renderResultFields(result.extracted_data);

        if (this.resultCard) {
            this.resultCard.classList.remove('hidden');
        }
    }

    /**
     * 更新置信度标签
     */
    updateConfidenceTag(confidence) {
        if (!this.confidenceTag) return;

        const percentage = Math.round((confidence || 0) * 100);
        this.confidenceTag.textContent = `置信度: ${percentage}%`;

        // 设置样式类
        this.confidenceTag.className = `confidence-tag ${this.getConfidenceClass(percentage)}`;
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
                    <label>${this.getFieldLabel(key)}:</label>
                    <span class="field-value" data-field="${key}">${this.formatFieldValue(key, value)}</span>
                `;
                this.resultGrid.appendChild(fieldDiv);
            }
        });

        // 如果没有有效数据，显示提示
        if (this.resultGrid.children.length === 0) {
            this.resultGrid.innerHTML = '<div class="text-muted text-center p-2">未识别到有效信息</div>';
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

        if (this.uploadZone) {
            this.uploadZone.classList.add('hidden');
        }

        if (this.errorMessage) {
            this.errorMessage.textContent = message;
        }

        if (this.errorState) {
            this.errorState.classList.remove('hidden');
        }
    }

    /**
     * 确认识别结果
     */
    async confirmResult() {
        if (!this.recognitionResult || !this.uploadedFile) {
            this.showError('没有可确认的识别结果');
            return;
        }

        const originalText = this.confirmBtn ? this.confirmBtn.textContent : '';

        try {
            // 禁用按钮
            this.setConfirmButtonState(true, '应用中...');

            // 1. 填充当事人表单
            this.fillClientForm(this.recognitionResult.extracted_data);

            // 2. 如果当事人已保存，创建证件记录
            const clientId = this.getClientId();
            if (clientId) {
                await this.createIdentityDocRecord(clientId);
            }

            // 显示成功消息并关闭对话框
            this.showSuccessMessage('识别结果已应用到表单');

            setTimeout(() => {
                this.closeDialog();
            }, 1500);

        } catch (error) {
            console.error('确认识别结果失败:', error);
            this.showError('应用识别结果失败: ' + error.message);
        } finally {
            // 恢复按钮状态
            this.setConfirmButtonState(false, originalText);
        }
    }

    /**
     * 设置确认按钮状态
     */
    setConfirmButtonState(disabled, text) {
        if (!this.confirmBtn) return;

        this.confirmBtn.disabled = disabled;
        if (text) {
            this.confirmBtn.textContent = text;
        }
    }

    /**
     * 填充当事人表单
     */
    fillClientForm(extractedData) {
        if (!extractedData) return;

        // 根据证件类型推断当事人类型
        const docType = this.docTypeSelect ? this.docTypeSelect.value : '';

        // 特殊处理：法定代表人/负责人身份证
        // 只填充 legal_representative_id_number 字段，不修改其他字段
        if (docType === 'legal_rep_id_card') {
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
        } else {
            // 其他证件 -> 自然人
            this.setFieldValue('client_type', 'natural');
            if (extractedData.name) {
                this.setFieldValue('name', extractedData.name);
            }
            if (extractedData.id_number) {
                this.setFieldValue('id_number', extractedData.id_number);
            }
        }

        // 通用字段
        if (extractedData.address) {
            this.setFieldValue('address', extractedData.address);
        }

        // 触发客户类型变更事件
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
        if (field && value !== undefined && value !== null) {
            if (field.type === 'checkbox') {
                field.checked = !!value;
            } else {
                field.value = value;
            }
            field.dispatchEvent(new Event('change'));
        }
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
        formData.append('doc_type', this.docTypeSelect.value);
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
     * 显示成功消息
     */
    showSuccessMessage(message) {
        // 可以在这里添加成功提示的UI
        console.log('Success:', message);

        // 简单的alert提示，可以后续改为更好的UI
        if (window.showMessage) {
            window.showMessage(message, 'success');
        } else {
            alert(message);
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

// 全局实例
let identityRecognition = null;

// 全局函数（供HTML模板调用）
function openIdentityDialog() {
    if (!identityRecognition) {
        identityRecognition = new IdentityRecognition();
    }
    identityRecognition.openDialog();
}

function closeIdentityDialog() {
    if (identityRecognition) {
        identityRecognition.closeDialog();
    }
}

function resetIdentityDialog() {
    if (identityRecognition) {
        identityRecognition.resetDialog();
    }
}

function confirmIdentityResult() {
    if (identityRecognition) {
        identityRecognition.confirmResult();
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 延迟初始化，确保DOM完全加载
    setTimeout(() => {
        identityRecognition = new IdentityRecognition();
    }, 100);
});

// 导出类供其他模块使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = IdentityRecognition;
}
