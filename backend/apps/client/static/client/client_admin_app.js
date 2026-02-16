/**
 * 当事人管理 Alpine.js 组件
 * 功能：文本解析、表单填充
 * 替代原有的 admin.js (IIFE 模式)
 */
function clientAdminApp() {
    return {
        // ========== 状态 ==========
        isDialogOpen: false,        // 对话框显示状态
        parseText: '',              // 待解析文本
        parseMultiple: false,       // 是否解析多个当事人
        isParsing: false,           // 解析中状态
        parseResult: null,          // 解析结果（单个当事人）
        multipleResults: [],        // 多个当事人解析结果
        showMultipleResults: false, // 显示多选结果对话框
        errorMessage: '',           // 错误信息
        successMessage: '',         // 成功信息

        // ========== 初始化 ==========
        init() {
            console.log('[ClientAdminApp] 初始化当事人管理组件');
            this.initFormEnhancements();
            this.initPasteListener();
        },

        // ========== 对话框管理 ==========

        /**
         * 打开文本解析对话框
         */
        openDialog() {
            this.isDialogOpen = true;
            this.resetState();
            // 延迟聚焦到文本框
            this.$nextTick(() => {
                const textarea = document.getElementById('parse-text-input');
                if (textarea) textarea.focus();
            });
        },

        /**
         * 关闭文本解析对话框
         */
        closeDialog() {
            this.isDialogOpen = false;
            this.resetState();
        },

        /**
         * 关闭多选结果对话框
         */
        closeMultipleResultsDialog() {
            this.showMultipleResults = false;
            this.multipleResults = [];
        },

        /**
         * 重置状态
         */
        resetState() {
            this.parseText = '';
            this.parseMultiple = false;
            this.isParsing = false;
            this.parseResult = null;
            this.errorMessage = '';
        },

        // ========== 文本解析 ==========

        /**
         * 解析当事人文本
         */
        async parseClientText() {
            if (!this.parseText.trim()) {
                this.showError('请输入要解析的文本内容');
                return;
            }

            this.isParsing = true;
            this.errorMessage = '';

            try {
                const response = await fetch('/api/v1/client/clients/parse-text', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({
                        text: this.parseText,
                        parse_multiple: this.parseMultiple
                    })
                });

                const data = await response.json();

                if (data.success) {
                    if (this.parseMultiple && data.clients) {
                        // 显示多选结果
                        this.multipleResults = data.clients;
                        this.showMultipleResults = true;
                        this.closeDialog();
                    } else if (data.client) {
                        // 单个当事人，直接填充
                        this.fillClientForm(data.client);
                        this.closeDialog();
                        this.showSuccess('文本解析成功，表单已自动填充');
                    }
                } else {
                    this.showError(data.error || '解析失败，请检查文本格式');
                }
            } catch (error) {
                console.error('[ClientAdminApp] 解析请求失败:', error);
                this.showError('解析请求失败，请检查网络连接');
            } finally {
                this.isParsing = false;
            }
        },

        /**
         * 选择多选结果中的一个当事人
         */
        selectClient(index) {
            const selectedClient = this.multipleResults[index];
            if (selectedClient) {
                this.fillClientForm(selectedClient);
                this.closeMultipleResultsDialog();
                this.showSuccess('已选择当事人信息并填充表单');
            }
        },

        // ========== 表单填充 ==========

        /**
         * 用解析的数据填充表单
         */
        fillClientForm(data) {
            // 填充基本字段
            this.setFieldValue('id_name', data.name);
            this.setFieldValue('id_phone', data.phone);
            this.setFieldValue('id_address', data.address);
            this.setFieldValue('id_id_number', data.id_number);
            this.setFieldValue('id_legal_representative', data.legal_representative);

            // 设置客户类型
            if (data.client_type) {
                const clientTypeField = document.getElementById('id_client_type');
                if (clientTypeField) {
                    clientTypeField.value = data.client_type;
                    // 触发 change 事件
                    clientTypeField.dispatchEvent(new Event('change'));
                }
            }

            // 高亮显示已填充的字段
            this.highlightFilledFields();
        },

        /**
         * 设置字段值
         */
        setFieldValue(fieldId, value) {
            if (value) {
                const field = document.getElementById(fieldId);
                if (field) {
                    field.value = value;
                }
            }
        },

        /**
         * 高亮显示已填充的字段
         */
        highlightFilledFields() {
            const fields = ['id_name', 'id_phone', 'id_address', 'id_id_number', 'id_legal_representative'];

            fields.forEach(fieldId => {
                const field = document.getElementById(fieldId);
                if (field && field.value) {
                    field.style.backgroundColor = '#e8f5e8';
                    field.style.borderColor = '#4caf50';

                    // 3秒后恢复正常样式
                    setTimeout(() => {
                        field.style.backgroundColor = '';
                        field.style.borderColor = '';
                    }, 3000);
                }
            });
        },

        // ========== 错误处理 ==========

        /**
         * 显示错误信息
         */
        showError(message) {
            this.errorMessage = message;
            // 5秒后自动清除
            setTimeout(() => {
                this.errorMessage = '';
            }, 5000);
        },

        /**
         * 显示成功信息
         */
        showSuccess(message) {
            this.successMessage = message;
            // 3秒后自动清除
            setTimeout(() => {
                this.successMessage = '';
            }, 3000);
        },

        // ========== 表单增强 ==========

        /**
         * 初始化表单增强功能
         */
        initFormEnhancements() {
            const clientTypeField = document.getElementById('id_client_type');
            if (clientTypeField) {
                clientTypeField.addEventListener('change', () => {
                    this.updateIdNumberLabel(clientTypeField.value);
                    this.toggleLegalRepFields(clientTypeField.value);
                });
                // 触发初始化
                this.updateIdNumberLabel(clientTypeField.value);
                this.toggleLegalRepFields(clientTypeField.value);
            }
        },

        /**
         * 更新证件号码标签
         */
        updateIdNumberLabel(clientType) {
            const label = document.querySelector('label[for="id_id_number"]');
            if (label) {
                label.textContent = clientType === 'natural' ? '身份证号码:' : '统一社会信用代码:';
            }
        },

        /**
         * 根据主体类型显示/隐藏法定代表人字段
         */
        toggleLegalRepFields(clientType) {
            const legalRepField = document.querySelector('.field-legal_representative');
            const legalRepIdField = document.querySelector('.field-legal_representative_id_number');

            if (clientType === 'natural') {
                // 自然人：隐藏法定代表人字段
                if (legalRepField) legalRepField.classList.add('hidden');
                if (legalRepIdField) legalRepIdField.classList.add('hidden');
            } else {
                // 法人/非法人组织：显示法定代表人字段
                if (legalRepField) legalRepField.classList.remove('hidden');
                if (legalRepIdField) legalRepIdField.classList.remove('hidden');
            }
        },

        /**
         * 初始化粘贴监听
         */
        initPasteListener() {
            const nameField = document.getElementById('id_name');
            if (nameField) {
                nameField.addEventListener('paste', (e) => {
                    setTimeout(() => {
                        const pastedText = nameField.value;
                        // 如果粘贴的内容包含多行或特殊格式，提示用户使用解析功能
                        if (pastedText && (pastedText.includes('\n') || pastedText.includes('：') || pastedText.includes(':'))) {
                            if (confirm('检测到您粘贴了格式化的当事人信息，是否使用自动解析功能？')) {
                                nameField.value = '';
                                this.parseText = pastedText;
                                this.openDialog();
                            }
                        }
                    }, 100);
                });
            }
        },

        // ========== 工具方法 ==========

        /**
         * 获取 CSRF Token
         */
        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        /**
         * 获取客户类型显示名称
         */
        getClientTypeDisplay(clientType) {
            const typeMap = {
                'natural': '自然人',
                'legal': '法人',
                'non_legal_org': '非法人组织'
            };
            return typeMap[clientType] || '自然人';
        },

        /**
         * 检查是否在添加页面
         */
        isAddPage() {
            return window.location.pathname.includes('/add/');
        }
    };
}
