// 发票识别 Alpine.js 组件
document.addEventListener('alpine:init', () => {
    Alpine.data('invoiceRecognition', () => ({
        // 状态
        uploading: false,
        progress: 0,
        results: [],
        dragging: false,
        uploadMessage: '',
        messageType: '',
        uploadedFiles: null,  // 保存上传的文件对象

        // 初始化
        init() {
            console.log('Invoice recognition component initialized');
        },

        // 计算属性
        get successCount() {
            return this.results.filter(r => r.success).length;
        },

        get failureCount() {
            return this.results.filter(r => !r.success).length;
        },

        get totalAmount() {
            return this.results
                .filter(r => r.success && r.data)
                .reduce((sum, r) => sum + parseFloat(r.data.total_amount || 0), 0);
        },

        // 文件选择处理
        handleFileSelect(event) {
            const files = Array.from(event.target.files || []);
            if (files.length > 0) {
                this.uploadFiles(files);
            }
        },

        // 拖拽处理
        handleDrop(event) {
            this.dragging = false;
            const files = Array.from(event.dataTransfer.files || []);
            if (files.length > 0) {
                this.uploadFiles(files);
            }
        },

        // 文件上传和识别
        async uploadFiles(files) {
            // 验证文件格式
            const validExtensions = ['.pdf', '.jpg', '.jpeg', '.png'];
            const invalidFiles = files.filter(file => {
                const ext = '.' + file.name.split('.').pop().toLowerCase();
                return !validExtensions.includes(ext);
            });

            if (invalidFiles.length > 0) {
                this.showMessage(
                    gettext('不支持的文件格式：') + invalidFiles.map(f => f.name).join(', '),
                    'error'
                );
                return;
            }

            // 验证文件大小 (20MB)
            const maxSize = 20 * 1024 * 1024;
            const oversizedFiles = files.filter(file => file.size > maxSize);
            if (oversizedFiles.length > 0) {
                this.showMessage(
                    gettext('文件大小超过限制（最大 20 MB）：') + oversizedFiles.map(f => f.name).join(', '),
                    'error'
                );
                return;
            }

            // 开始上传
            this.uploading = true;
            this.progress = 0;
            this.results = [];
            this.uploadMessage = '';

            // 保存文件对象供后续使用
            this.uploadedFiles = files;

            try {
                const formData = new FormData();
                files.forEach(file => {
                    formData.append('files', file);
                });

                // 获取 CSRF token
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;

                // 调用快速识别 API
                const response = await fetch('/api/v1/invoice-recognition/quick-recognize', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrfToken
                    },
                    body: formData
                });

                this.progress = 100;

                if (!response.ok) {
                    throw new Error(gettext('识别失败，请重试'));
                }

                const data = await response.json();
                this.results = data.results || [];

                // 更新表单字段
                if (this.successCount > 0) {
                    this.updateInvoicedAmount();
                    this.addInvoiceRows();
                    this.showMessage(
                        gettext('识别完成！成功：') + this.successCount +
                        gettext('，失败：') + this.failureCount,
                        this.failureCount > 0 ? 'warning' : 'success'
                    );
                } else {
                    this.showMessage(gettext('所有文件识别失败'), 'error');
                }

            } catch (error) {
                console.error('Upload error:', error);
                this.showMessage(error.message || gettext('上传失败，请重试'), 'error');
            } finally {
                this.uploading = false;
            }
        },

        // 更新已开票金额
        updateInvoicedAmount() {
            const invoicedAmountField = document.querySelector('#id_invoiced_amount');
            if (!invoicedAmountField) return;

            const currentAmount = parseFloat(invoicedAmountField.value || 0);
            const newAmount = currentAmount + this.totalAmount;
            invoicedAmountField.value = newAmount.toFixed(2);

            // 触发 change 事件以更新开票状态
            invoicedAmountField.dispatchEvent(new Event('change', { bubbles: true }));

            // 计算并更新开票状态
            this.calculateInvoiceStatus();
        },

        // 计算开票状态
        calculateInvoiceStatus() {
            const invoicedAmountField = document.querySelector('#id_invoiced_amount');
            const paymentAmountField = document.querySelector('#id_amount');
            const invoiceStatusField = document.querySelector('#id_invoice_status');

            if (!invoicedAmountField || !paymentAmountField || !invoiceStatusField) return;

            const invoicedAmount = parseFloat(invoicedAmountField.value || 0);
            const paymentAmount = parseFloat(paymentAmountField.value || 0);

            if (invoicedAmount > paymentAmount) {
                this.showMessage(gettext('警告：开票金额超过收款金额'), 'warning');
            }

            // 状态值根据实际模型定义调整
            if (invoicedAmount === 0) {
                invoiceStatusField.value = 'uninvoiced';
            } else if (invoicedAmount < paymentAmount) {
                invoiceStatusField.value = 'invoiced_partial';
            } else {
                invoiceStatusField.value = 'invoiced_full';
            }
        },

        // 动态添加发票行
        addInvoiceRows() {
            const successResults = this.results.filter(r => r.success && r.data);
            if (successResults.length === 0) return;

            // 查找 InvoiceInline 表单集
            const inlineGroup = document.querySelector('.inline-group[id*="invoice"]');
            if (!inlineGroup) {
                console.warn('Invoice inline not found');
                return;
            }

            // 获取当前表单数量
            const totalFormsInput = inlineGroup.querySelector('[name$="-TOTAL_FORMS"]');
            if (!totalFormsInput) {
                console.warn('TOTAL_FORMS input not found');
                return;
            }

            let totalForms = parseInt(totalFormsInput.value || 0);

            // 查找表格 tbody
            const tbody = inlineGroup.querySelector('tbody.djn-tbody:not(.djn-empty-form)');
            if (!tbody) {
                console.warn('Invoice table body not found');
                return;
            }

            // 查找所有现有行
            const rows = tbody.querySelectorAll('tr.djn-tr');
            if (rows.length === 0) {
                console.warn('No invoice rows found');
                return;
            }

            // 使用最后一行作为模板
            const templateRow = rows[rows.length - 1];

            // 为每个成功的识别结果添加行
            successResults.forEach((result, index) => {
                const newRow = templateRow.cloneNode(true);
                const formIndex = totalForms + index;

                // 更新所有字段的 name 和 id
                newRow.querySelectorAll('input, select, textarea').forEach(field => {
                    if (field.name) {
                        field.name = field.name.replace(/-\d+-/, `-${formIndex}-`);
                    }
                    if (field.id) {
                        field.id = field.id.replace(/-\d+-/, `-${formIndex}-`);
                    }
                    // 清空值（除了隐藏字段）
                    if (field.type !== 'hidden' && !field.name.includes('DELETE')) {
                        field.value = '';
                    }
                    // 清空 DELETE 标记
                    if (field.name && field.name.includes('DELETE')) {
                        field.checked = false;
                    }
                });

                // 清空所有只读显示元素（<p>标签）
                newRow.querySelectorAll('td p').forEach(p => {
                    p.textContent = '-';
                });

                // 填充识别结果
                const data = result.data;

                // 填充文件到file input（使用DataTransfer API）
                const fileInput = newRow.querySelector(`input[type="file"][name*="-file"]`);
                if (fileInput && this.uploadedFiles) {
                    // 找到对应的原始文件
                    const originalFile = this.uploadedFiles.find(f => f.name === result.filename);
                    if (originalFile) {
                        try {
                            const dataTransfer = new DataTransfer();
                            dataTransfer.items.add(originalFile);
                            fileInput.files = dataTransfer.files;
                            console.log(`File attached to input: ${result.filename}`);
                        } catch (e) {
                            console.error('Failed to attach file:', e);
                        }
                    }
                }

                // 价税合计
                const totalField = newRow.querySelector(`input[name*="-total_amount"]`);
                if (totalField && data.total_amount) {
                    totalField.value = parseFloat(data.total_amount).toFixed(2);
                }

                // 插入新行
                tbody.appendChild(newRow);
            });

            // 更新总表单数
            totalFormsInput.value = totalForms + successResults.length;

            console.log(`Added ${successResults.length} invoice rows with files`);
        },

        // 显示消息        // 显示消息
        showMessage(message, type) {
            this.uploadMessage = message;
            this.messageType = type;

            // 3秒后自动清除成功消息
            if (type === 'success') {
                setTimeout(() => {
                    this.uploadMessage = '';
                }, 3000);
            }
        }
    }));
});

// 国际化辅助函数（如果 Django i18n 未加载）
if (typeof gettext === 'undefined') {
    window.gettext = function(text) {
        return text;
    };
}
