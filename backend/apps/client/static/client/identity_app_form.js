/**
 * 身份材料智能识别 Alpine.js 组件 - 表单填充模块
 * 功能：结果处理、表单填充、Inline 表单填充、日期解析、字段操作、证件记录、消息提示
 * 依赖：identity_app.js（必须先加载）
 */

window._identityFormMethods = {
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
                    fileNameSpan.style.cssText = 'color: var(--fc-success-text); font-size: 12px; margin-left: 8px;';
                    uploadInput.parentNode.appendChild(fileNameSpan);
                }
                fileNameSpan.textContent = '✓ ' + this.uploadedFile.name;

            } catch (e) {
                console.error('设置文件失败:', e);
                let fileHint = targetRow.querySelector('.file-hint');
                if (!fileHint) {
                    fileHint = document.createElement('div');
                    fileHint.className = 'file-hint';
                    fileHint.style.cssText = 'color: var(--fc-warning-text); font-size: 12px; margin: 5px 0; padding: 8px; background: var(--fc-warning-bg); border: 1px solid var(--fc-warning-border); border-radius: 4px;';
                    uploadInput.parentNode.appendChild(fileHint);
                }
                fileHint.innerHTML = '⚠ 请点击"选择文件"按钮，选择文件: <strong>' + this.uploadedFile.name + '</strong>';
            }
        }

        // 高亮 inline 行
        targetRow.style.backgroundColor = 'var(--fc-success-bg)';
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
            field.style.backgroundColor = 'var(--fc-success-bg)';
            field.style.borderColor = 'var(--fc-success-text)';
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

    // ========== 消息提示 ==========

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
        const bgColor = type === 'success' ? 'var(--fc-success-text)' : 'var(--fc-error-text)';
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${bgColor};
            color: var(--fc-text-on-primary);
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
    }
};
