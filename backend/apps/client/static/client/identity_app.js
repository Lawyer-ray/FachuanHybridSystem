/**
 * 身份材料智能识别 Alpine.js 组件
 * 功能：文件上传、OCR 识别、表单填充
 * 支持两种模式：对话框模式（dialog）和内联模式（inline）
 * 替代原有的 identity_recognition.js 和 identity_recognition_inline.js
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 8.1, 8.2, 8.3
 */

function identityApp(config = {}) {
    return {
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
        enableOllama: false,        // 身份证场景是否启用 Ollama 兜底
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
            this.enableOllama = false;
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
            formData.append('doc_type', docType);
            formData.append('enable_ollama', this.shouldEnableOllama(docType) ? 'true' : 'false');

            this.loadingText = '正在识别证件...';

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

        isIdCardDocType(docType) {
            return docType === 'id_card' || docType === 'legal_rep_id_card';
        },

        shouldEnableOllama(docType) {
            if (!this.isIdCardDocType(docType)) {
                return true;
            }
            return !!this.enableOllama;
        },

        // ========== 结果处理 ==========

        /**
         * 获取置信度样式类
         * @returns {string} - CSS 类名
         */
        getConfidenceClass() {
            if (this.confidence >= 80) return 'high';
            if (this.confidence >= 60) return 'medium';
            return 'low';
        },

        /**
         * 获取字段标签
         * @param {string} key - 字段键名
         * @returns {string} - 字段标签
         */
        getFieldLabel(key) {
            return this.fieldLabels[key] || key;
        },

        /**
         * 获取提取的数据条目
         * @returns {Array} - 数据条目数组
         */
        getExtractedDataEntries() {
            if (!this.recognitionResult || !this.recognitionResult.extracted_data) {
                return [];
            }

            return Object.entries(this.recognitionResult.extracted_data)
                .filter(([key, value]) => value && value.toString().trim())
                .map(([key, value]) => ({
                    key,
                    label: this.getFieldLabel(key),
                    value: this.formatFieldValue(key, value)
                }));
        },

        /**
         * 格式化字段值
         * @param {string} key - 字段键名
         * @param {any} value - 字段值
         * @returns {string} - 格式化后的值
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
        },

        // ========== 表单填充 ==========

        /**
         * 确认识别结果
         */
        async confirmResult() {
            if (!this.recognitionResult || !this.uploadedFile) {
                this.displayError('没有可确认的识别结果');
                return;
            }

            this.isConfirming = true;

            try {
                // 1. 填充当事人表单
                this.fillClientForm(this.recognitionResult.extracted_data);

                // 2. inline 模式：填充证件文件 inline 表单
                if (this.mode === 'inline') {
                    this.fillIdentityDocInline(this.docType, this.recognitionResult.extracted_data);
                }

                // 3. 如果当事人已保存，创建证件记录（仅 dialog 模式）
                if (this.mode === 'dialog') {
                    const clientId = this.getClientId();
                    if (clientId) {
                        await this.createIdentityDocRecord(clientId);
                    }
                }

                // 显示成功消息
                this.showSuccessMessage('识别结果已应用到表单');

                // dialog 模式：关闭对话框
                if (this.mode === 'dialog') {
                    setTimeout(() => {
                        this.closeDialog();
                    }, 1500);
                }

            } catch (error) {
                console.error('确认识别结果失败:', error);
                this.displayError('应用识别结果失败: ' + error.message);
            } finally {
                this.isConfirming = false;
            }
        },

        /**
         * 填充当事人表单
         * @param {Object} extractedData - 提取的数据
         */
        fillClientForm(extractedData) {
            if (!extractedData) return;

            // 特殊处理：法定代表人/负责人身份证
            if (this.docType === 'legal_rep_id_card') {
                const idNumber = extractedData.id_number || extractedData.id_card_number || '';
                if (idNumber) {
                    this.setFieldValue('legal_representative_id_number', idNumber);
                }

                // 高亮填充的字段
                this.highlightField('legal_representative_id_number');
                return;
            }

            if (this.docType === 'business_license') {
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
                // 支持多种证件号码字段名
                const idNumber = extractedData.id_number || extractedData.id_card_number ||
                               extractedData.passport_number || extractedData.permit_number;
                if (idNumber) {
                    this.setFieldValue('id_number', idNumber);
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
        },

        // ========== Inline 模式：证件文件 Inline 填充 ==========

        /**
         * 填充证件文件 inline 表单（inline 模式专用）
         * @param {string} docType - 证件类型
         * @param {Object} extractedData - 提取的数据
         */
        fillIdentityDocInline(docType, extractedData) {
            console.log('填充证件文件 inline, docType:', docType);

            // 法定代表人/负责人身份证：新建记录
            if (docType === 'legal_rep_id_card') {
                this.fillIdentityDocInlineNew(docType, extractedData);
                return;
            }

            // 其他证件类型：填充第一个空行或第一行
            const inlineRows = document.querySelectorAll('.dynamic-identity_docs');
            let targetRow = null;

            // 查找第一个空的 inline 行
            for (let i = 0; i < inlineRows.length; i++) {
                const row = inlineRows[i];
                const uploadInput = row.querySelector('input[type="file"]');

                if (uploadInput && (!uploadInput.files || uploadInput.files.length === 0)) {
                    targetRow = row;
                    break;
                }
            }

            // 如果没有找到空行，使用第一行
            if (!targetRow && inlineRows.length > 0) {
                targetRow = inlineRows[0];
            }

            if (!targetRow) {
                console.log('未找到证件文件 inline 行');
                return;
            }

            this.fillTargetRow(targetRow, docType, extractedData);
        },

        /**
         * 新建证件文件 inline 记录（用于法定代表人/负责人身份证等）
         * @param {string} docType - 证件类型
         * @param {Object} extractedData - 提取的数据
         */
        fillIdentityDocInlineNew(docType, extractedData) {
            console.log('新建证件文件 inline 记录, docType:', docType);

            const inlineRows = document.querySelectorAll('.dynamic-identity_docs');
            let targetRow = null;

            // 查找第一个空的 inline 行
            for (let i = 0; i < inlineRows.length; i++) {
                const row = inlineRows[i];
                const docTypeSelect = row.querySelector('select[name$="-doc_type"]');
                const uploadInput = row.querySelector('input[type="file"]');
                const existingFile = row.querySelector('a[href*="media"]');

                const isEmpty = (!docTypeSelect || !docTypeSelect.value) &&
                               (!uploadInput || !uploadInput.files || uploadInput.files.length === 0) &&
                               !existingFile;

                if (isEmpty) {
                    targetRow = row;
                    break;
                }
            }

            // 如果没有找到空行，尝试点击"添加另一个"按钮
            if (!targetRow) {
                const addButton = document.querySelector('.add-row a, .inline-group .add-row a, [data-inline-type="tabular"] .add-row a') ||
                                 document.querySelector('.djn-add-item a, .grp-add-item a, .inline-related .add-row a');

                if (addButton) {
                    console.log('点击添加按钮创建新行');
                    addButton.click();

                    // 等待新行创建后再填充
                    setTimeout(() => {
                        const newRows = document.querySelectorAll('.dynamic-identity_docs');
                        if (newRows.length > inlineRows.length) {
                            targetRow = newRows[newRows.length - 1];
                        } else {
                            targetRow = newRows[newRows.length - 1];
                        }
                        if (targetRow) {
                            this.fillTargetRow(targetRow, docType, extractedData);
                        }
                    }, 200);
                    return;
                } else if (inlineRows.length > 0) {
                    targetRow = inlineRows[inlineRows.length - 1];
                }
            }

            if (targetRow) {
                this.fillTargetRow(targetRow, docType, extractedData);
            }
        },

        /**
         * 填充目标 inline 行
         * @param {Element} targetRow - 目标行元素
         * @param {string} docType - 证件类型
         * @param {Object} extractedData - 提取的数据
         */
        fillTargetRow(targetRow, docType, extractedData) {
            console.log('填充目标行:', targetRow);

            // 设置证件类型
            const inlineDocTypeSelect = targetRow.querySelector('select[name$="-doc_type"]');
            if (inlineDocTypeSelect && docType) {
                inlineDocTypeSelect.value = docType;
                console.log('设置 inline 证件类型:', docType);
            }

            // 设置到期日期
            const expiryDateInput = targetRow.querySelector('input[name$="-expiry_date"]');
            if (expiryDateInput && extractedData.expiry_date) {
                const expiryDate = this.parseExpiryDate(extractedData.expiry_date);
                if (expiryDate) {
                    expiryDateInput.value = expiryDate;
                    console.log('设置到期日期:', expiryDate);
                }
            }

            // 设置上传文件
            const uploadInput = targetRow.querySelector('input[type="file"]');
            if (uploadInput && this.uploadedFile) {
                try {
                    if (window.DataTransfer) {
                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(this.uploadedFile);
                        uploadInput.files = dataTransfer.files;
                        console.log('使用 DataTransfer 设置文件成功:', this.uploadedFile.name);
                    }

                    uploadInput.dispatchEvent(new Event('change', { bubbles: true }));

                    // 显示文件名
                    let fileNameSpan = targetRow.querySelector('.file-name-display');
                    if (!fileNameSpan) {
                        fileNameSpan = document.createElement('span');
                        fileNameSpan.className = 'file-name-display';
                        fileNameSpan.style.cssText = 'color: #4caf50; font-size: 12px; margin-left: 8px;';
                        uploadInput.parentNode.appendChild(fileNameSpan);
                    }
                    fileNameSpan.textContent = '✓ ' + this.uploadedFile.name;

                } catch (e) {
                    console.error('设置文件失败:', e);
                    let fileHint = targetRow.querySelector('.file-hint');
                    if (!fileHint) {
                        fileHint = document.createElement('div');
                        fileHint.className = 'file-hint';
                        fileHint.style.cssText = 'color: #ff9800; font-size: 12px; margin: 5px 0; padding: 8px; background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px;';
                        uploadInput.parentNode.appendChild(fileHint);
                    }
                    fileHint.innerHTML = '⚠ 请点击"选择文件"按钮，选择文件: <strong>' + this.uploadedFile.name + '</strong>';
                }
            }

            // 高亮 inline 行
            targetRow.style.backgroundColor = '#e8f5e8';
            setTimeout(() => {
                targetRow.style.backgroundColor = '';
            }, 3000);
        },

        /**
         * 解析到期日期，只取最后的日期
         * @param {string} dateStr - 日期字符串
         * @returns {string|null} - 格式化后的日期 (YYYY/MM/DD)
         */
        parseExpiryDate(dateStr) {
            if (!dateStr) return null;

            // 处理 "长期" 的情况
            if (dateStr.includes('长期')) {
                return null;
            }

            // 处理日期范围格式，只取最后的日期
            const separators = ['至', '-', '~', '—', '到'];
            let finalDate = dateStr;

            for (const sep of separators) {
                if (dateStr.includes(sep)) {
                    const parts = dateStr.split(sep);
                    if (parts.length >= 2) {
                        const lastPart = parts[parts.length - 1].trim();
                        if (/\d{4}/.test(lastPart)) {
                            finalDate = lastPart;
                            break;
                        }
                    }
                }
            }

            // 标准化日期格式
            finalDate = finalDate.replace(/\./g, '-').replace(/\//g, '-');

            // 验证日期格式并转换为 YYYY/MM/DD
            const dateMatch = finalDate.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
            if (dateMatch) {
                const year = dateMatch[1];
                const month = dateMatch[2].padStart(2, '0');
                const day = dateMatch[3].padStart(2, '0');
                return `${year}/${month}/${day}`;
            }

            return null;
        },

        /**
         * 设置表单字段值
         * @param {string} fieldName - 字段名
         * @param {any} value - 字段值
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
        },

        /**
         * 高亮单个字段
         * @param {string} fieldName - 字段名
         */
        highlightField(fieldName) {
            const field = document.getElementById('id_' + fieldName);
            if (field && field.value) {
                field.style.backgroundColor = '#e8f5e8';
                field.style.borderColor = '#4caf50';
                field.style.transition = 'all 0.3s ease';

                setTimeout(() => {
                    field.style.backgroundColor = '';
                    field.style.borderColor = '';
                }, 3000);
            }
        },

        /**
         * 高亮所有填充的字段
         */
        highlightFilledFields() {
            const fieldNames = ['name', 'id_number', 'address', 'legal_representative'];
            fieldNames.forEach(fieldName => this.highlightField(fieldName));
        },

        // ========== 证件记录 ==========

        /**
         * 获取当前当事人ID（如果已保存）
         * @returns {string|null} - 当事人ID
         */
        getClientId() {
            const url = window.location.pathname;
            const match = url.match(/\/admin\/client\/client\/(\d+)\/change\//);
            return match ? match[1] : null;
        },

        /**
         * 创建证件记录
         * @param {string} clientId - 当事人ID
         */
        async createIdentityDocRecord(clientId) {
            const formData = new FormData();
            formData.append('client', clientId);
            formData.append('doc_type', this.docType);
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
        },

        // ========== 工具方法 ==========

        /**
         * 显示成功消息
         * @param {string} message - 成功消息
         */
        showSuccessMessage(message) {
            console.log('Success:', message);

            // inline 模式：显示页面内 toast 提示
            if (this.mode === 'inline') {
                this.showInlineToast(message, 'success');
                return;
            }

            // dialog 模式：使用全局消息或 alert
            if (window.showMessage) {
                window.showMessage(message, 'success');
            } else {
                alert(message);
            }
        },

        /**
         * 显示页面内 toast 提示（inline 模式专用）
         * @param {string} message - 消息内容
         * @param {string} type - 消息类型 ('success' | 'error')
         */
        showInlineToast(message, type = 'success') {
            const toast = document.createElement('div');
            const bgColor = type === 'success' ? '#4caf50' : '#f44336';
            toast.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: ${bgColor};
                color: #fff;
                padding: 12px 20px;
                border-radius: 6px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                z-index: 9999;
                font-size: 14px;
                animation: fadeIn 0.3s ease;
            `;
            toast.textContent = message;
            document.body.appendChild(toast);

            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transition = 'opacity 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }, 2000);
        },

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
}
