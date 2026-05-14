/**
 * Contract detail Alpine app.
 *
 * Keeps the existing document-generation behavior and adds CRUD operations
 * for contract payment records inside the finance tab.
 */

function contractDetailApp(config = {}) {
    const contractId = config.contractId;
    const storageKey = 'contractDetailTab';
    const reloadToastKey = 'contractDetailToast';

    return {
        activeTab: localStorage.getItem(storageKey) || 'basic',

        generating: false,
        generatingType: null,
        splitFee: true,

        folderUnlocked: false,
        get folderLockIcon() {
            const locked = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>';
            const unlocked = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 019.9-1"/></svg>';
            return this.folderUnlocked ? unlocked : locked;
        },

        showAgreementDialog: false,
        selectedAgreementId: null,

        showPreviewDialog: false,
        showAgreementPreviewSelect: false,
        previewAgreementId: null,
        previewTitle: '',
        previewRows: [],
        isLoadingPreview: false,
        previewEditMode: false,
        previewHasOverrides: false,
        previewContractId: null,
        previewTemplateSubtype: null,

        paymentDialogOpen: false,
        paymentDialogMode: 'create',
        paymentSubmitting: false,
        paymentDeleting: false,
        deletePaymentDialogOpen: false,
        deletePaymentTargetId: null,
        deletePaymentSummary: '',
        paymentForm: {
            id: null,
            amount: '',
            received_at: '',
            invoice_status: 'UNINVOICED',
            invoiced_amount: '0.00',
            note: '',
        },

        toasts: [],

        init() {
            this.$watch('activeTab', (value) => {
                localStorage.setItem(storageKey, value);
            });

            this.consumeReloadToast();

            window.addEventListener('contract-folder-scan-needs-binding', () => {
                this.activeTab = 'documents';
                this.showToast('Please bind the contract folder first.', 'error');
            });

            this.$el.addEventListener('archive-preview-open', (e) => {
                const { contractId: cid, templateSubtype, templateName, editMode } = e.detail;
                this.previewTitle = `${templateName} - Preview`;
                this.previewRows = [];
                this.isLoadingPreview = true;
                this.showPreviewDialog = true;
                this.previewEditMode = false;
                this.previewHasOverrides = false;
                this.previewContractId = cid;
                this.previewTemplateSubtype = templateSubtype;
                const shouldEdit = editMode === true;

                fetch(`/api/v1/documents/contracts/${cid}/archive-preview?template_subtype=${encodeURIComponent(templateSubtype)}`)
                    .then((r) => r.json())
                    .then((result) => {
                        if (result.success && result.data) {
                            this.previewRows = result.data.map((row) => ({ ...row, editValue: row.value || '' }));
                            this.previewHasOverrides = !!result.has_overrides;
                            if (shouldEdit) {
                                this.previewEditMode = true;
                            }
                        } else {
                            this.showToast(`Preview failed: ${result.error || 'Unknown error'}`, 'error');
                            this.showPreviewDialog = false;
                        }
                    })
                    .catch((err) => {
                        this.showToast(`Preview request failed: ${err.message}`, 'error');
                        this.showPreviewDialog = false;
                    })
                    .finally(() => {
                        this.isLoadingPreview = false;
                    });
            });
        },

        showToast(message, type = 'success') {
            const toast = { message, type, show: true };
            this.toasts.push(toast);

            setTimeout(() => {
                toast.show = false;
                setTimeout(() => {
                    const index = this.toasts.indexOf(toast);
                    if (index > -1) {
                        this.toasts.splice(index, 1);
                    }
                }, 300);
            }, 3000);
        },

        queueReloadToast(message, type = 'success') {
            try {
                sessionStorage.setItem(reloadToastKey, JSON.stringify({ message, type }));
            } catch (err) {
                console.warn('save reload toast failed', err);
            }
            window.location.reload();
        },

        consumeReloadToast() {
            try {
                const raw = sessionStorage.getItem(reloadToastKey);
                if (!raw) return;

                sessionStorage.removeItem(reloadToastKey);
                const parsed = JSON.parse(raw);
                if (parsed && parsed.message) {
                    this.showToast(parsed.message, parsed.type || 'success');
                }
            } catch (err) {
                sessionStorage.removeItem(reloadToastKey);
                console.warn('consume reload toast failed', err);
            }
        },

        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        buildPaymentForm() {
            return {
                id: null,
                amount: '',
                received_at: this.getTodayString(),
                invoice_status: 'UNINVOICED',
                invoiced_amount: '0.00',
                note: '',
            };
        },

        getTodayString() {
            const now = new Date();
            const tzOffset = now.getTimezoneOffset() * 60000;
            return new Date(now.getTime() - tzOffset).toISOString().slice(0, 10);
        },

        closePaymentDialog() {
            if (this.paymentSubmitting) return;
            this.paymentDialogOpen = false;
        },

        openCreatePaymentDialog() {
            this.paymentDialogMode = 'create';
            this.paymentForm = this.buildPaymentForm();
            this.paymentDialogOpen = true;
        },

        openEditPaymentDialogFromTrigger(event) {
            const button = event.currentTarget;
            this.paymentDialogMode = 'edit';
            this.paymentForm = {
                id: Number(button.dataset.id),
                amount: button.dataset.amount || '',
                received_at: button.dataset.receivedAt || '',
                invoice_status: button.dataset.invoiceStatus || 'UNINVOICED',
                invoiced_amount: button.dataset.invoicedAmount || '0.00',
                note: button.dataset.note || '',
            };
            this.paymentDialogOpen = true;
        },

        openDeletePaymentDialogFromTrigger(event) {
            const button = event.currentTarget;
            const amount = button.dataset.amount || '';
            const receivedAt = button.dataset.receivedAt || '';
            this.deletePaymentTargetId = Number(button.dataset.id);
            this.deletePaymentSummary = `Delete payment record on ${receivedAt || '-'} (Yuan ${amount || '0.00'})?`;
            this.deletePaymentDialogOpen = true;
        },

        closeDeletePaymentDialog() {
            if (this.paymentDeleting) return;
            this.deletePaymentDialogOpen = false;
            this.deletePaymentTargetId = null;
            this.deletePaymentSummary = '';
        },

        normalizePaymentPayload() {
            const amount = Number.parseFloat(this.paymentForm.amount);
            const invoicedAmountRaw = this.paymentForm.invoiced_amount === '' ? '0' : this.paymentForm.invoiced_amount;
            const invoicedAmount = Number.parseFloat(invoicedAmountRaw);
            const receivedAt = (this.paymentForm.received_at || '').trim();
            const invoiceStatus = this.paymentForm.invoice_status || 'UNINVOICED';
            const note = (this.paymentForm.note || '').trim();

            if (!Number.isFinite(amount) || amount <= 0) {
                throw new Error('Payment amount must be greater than 0.');
            }
            if (!receivedAt) {
                throw new Error('Please choose a payment date.');
            }
            if (!Number.isFinite(invoicedAmount) || invoicedAmount < 0) {
                throw new Error('Invoiced amount cannot be negative.');
            }
            if (invoicedAmount > amount) {
                throw new Error('Invoiced amount cannot be greater than payment amount.');
            }

            return {
                contract_id: contractId,
                amount,
                received_at: receivedAt,
                invoice_status: invoiceStatus,
                invoiced_amount: invoiceStatus === 'UNINVOICED' ? 0 : invoicedAmount,
                note: note || null,
                confirm: true,
            };
        },

        async requestJson(url, options = {}, fallbackMessage = 'Request failed.') {
            const response = await fetch(url, {
                credentials: 'same-origin',
                ...options,
                headers: {
                    'X-CSRFToken': this.getCsrfToken(),
                    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
                    ...(options.headers || {}),
                },
            });

            let data = null;
            const text = await response.text();
            if (text) {
                try {
                    data = JSON.parse(text);
                } catch (err) {
                    data = { detail: text };
                }
            }

            if (!response.ok) {
                const message = this.extractErrorMessage(data, fallbackMessage);
                throw new Error(message);
            }

            return data;
        },

        extractErrorMessage(data, fallbackMessage) {
            if (!data) return fallbackMessage;
            if (typeof data === 'string') return data;
            if (Array.isArray(data.detail) && data.detail.length > 0) {
                const first = data.detail[0];
                if (typeof first === 'string') return first;
                if (first && typeof first.msg === 'string') return first.msg;
            }
            if (typeof data.detail === 'string') return data.detail;
            if (typeof data.message === 'string') return data.message;
            if (typeof data.error === 'string') return data.error;
            return fallbackMessage;
        },

        async submitPayment() {
            if (this.paymentSubmitting) return;

            let payload;
            try {
                payload = this.normalizePaymentPayload();
            } catch (err) {
                this.showToast(err.message || 'Form validation failed.', 'error');
                return;
            }

            this.paymentSubmitting = true;

            try {
                if (this.paymentDialogMode === 'edit' && this.paymentForm.id) {
                    const updatePayload = { ...payload };
                    delete updatePayload.contract_id;
                    await this.requestJson(
                        `/api/v1/contracts/finance/payments/${this.paymentForm.id}`,
                        {
                            method: 'PUT',
                            body: JSON.stringify(updatePayload),
                        },
                        'Failed to update payment record.'
                    );
                    this.queueReloadToast('Payment record updated.');
                } else {
                    await this.requestJson(
                        '/api/v1/contracts/finance/payments',
                        {
                            method: 'POST',
                            body: JSON.stringify(payload),
                        },
                        'Failed to create payment record.'
                    );
                    this.queueReloadToast('Payment record created.');
                }
            } catch (err) {
                this.showToast(err.message || 'Operation failed.', 'error');
            } finally {
                this.paymentSubmitting = false;
            }
        },

        async deletePayment() {
            if (this.paymentDeleting || !this.deletePaymentTargetId) return;

            this.paymentDeleting = true;
            try {
                await this.requestJson(
                    `/api/v1/contracts/finance/payments/${this.deletePaymentTargetId}?confirm=true`,
                    { method: 'DELETE' },
                    'Failed to delete payment record.'
                );
                this.queueReloadToast('Payment record deleted.');
            } catch (err) {
                this.showToast(err.message || 'Delete failed.', 'error');
            } finally {
                this.paymentDeleting = false;
            }
        },

        enterPreviewEditMode() {
            this.previewEditMode = true;
            this.previewRows.forEach((row) => {
                if (!row.editValue && row.editValue !== '') {
                    row.editValue = row.value || '';
                }
            });
        },

        cancelPreviewEdit() {
            this.previewEditMode = false;
        },

        async revertPreviewOverrides() {
            if (!this.previewContractId || !this.previewTemplateSubtype) return;

            try {
                const data = await this.requestJson(
                    `/api/v1/documents/contracts/${this.previewContractId}/archive-placeholder-overrides?template_subtype=${encodeURIComponent(this.previewTemplateSubtype)}`,
                    { method: 'DELETE' },
                    'Failed to revert preview overrides.'
                );

                if (data.success) {
                    this.previewHasOverrides = false;
                    this.showPreviewDialog = false;
                    setTimeout(() => {
                        const app = document.querySelector('.contract-detail-page');
                        if (app) {
                            app.dispatchEvent(new CustomEvent('archive-preview-open', {
                                detail: {
                                    contractId: this.previewContractId,
                                    templateSubtype: this.previewTemplateSubtype,
                                    templateName: this.previewTitle.replace(' - Preview', ''),
                                    editMode: false,
                                },
                                bubbles: true,
                            }));
                        }
                    }, 200);
                    this.showToast('Preview overrides reverted.', 'success');
                } else {
                    this.showToast(`Revert failed: ${data.error || 'Unknown error'}`, 'error');
                }
            } catch (err) {
                this.showToast(`Revert request failed: ${err.message}`, 'error');
            }
        },

        async savePreviewOverrides() {
            if (!this.previewContractId || !this.previewTemplateSubtype) return;

            const overrides = {};
            this.previewRows.forEach((row) => {
                const editVal = (row.editValue || '').trim();
                const origVal = (row.value || '').trim();
                if (editVal !== origVal) {
                    overrides[row.key] = editVal;
                }
            });

            try {
                const data = await this.requestJson(
                    `/api/v1/documents/contracts/${this.previewContractId}/archive-placeholder-overrides?template_subtype=${encodeURIComponent(this.previewTemplateSubtype)}`,
                    {
                        method: 'POST',
                        body: JSON.stringify({ overrides }),
                    },
                    'Failed to save preview overrides.'
                );

                if (data.success) {
                    this.previewRows.forEach((row) => {
                        if (row.editValue !== undefined && row.editValue.trim() !== '') {
                            row.value = row.editValue;
                            row.status = 'ok';
                        }
                    });
                    this.previewEditMode = false;
                    this.previewHasOverrides = true;
                    this.showToast('Preview overrides saved.', 'success');
                } else {
                    this.showToast(`Save failed: ${data.error || 'Unknown error'}`, 'error');
                }
            } catch (err) {
                this.showToast(`Save request failed: ${err.message}`, 'error');
            }
        },

        async handleDownloadResponse(response, defaultFilename) {
            const blob = await response.blob();
            const contentDisposition = response.headers.get('content-disposition');
            let filename = defaultFilename;

            if (contentDisposition) {
                const utf8Match = contentDisposition.match(/filename\*=UTF-8''(.+)/);
                if (utf8Match) {
                    filename = decodeURIComponent(utf8Match[1]);
                } else {
                    const simpleMatch = contentDisposition.match(/filename="?([^";\n]+)"?/);
                    if (simpleMatch) {
                        filename = simpleMatch[1];
                    }
                }
            }

            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(link);

            return filename;
        },

        async generateContract() {
            if (this.generating || !contractId) return;

            this.generating = true;
            this.generatingType = 'contract';

            try {
                const response = await fetch(`/api/v1/documents/contracts/${contractId}/download?split_fee=${this.splitFee}`);
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.message || errorData.detail || 'Generate failed.');
                }

                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    const data = await response.json();
                    this.showToast(data.message || 'Contract generated and saved.', 'success');
                } else {
                    await this.handleDownloadResponse(response, 'contract.docx');
                    this.showToast('Contract generated.', 'success');
                }
            } catch (error) {
                console.error('generate contract failed', error);
                this.showToast(error.message || 'Generate contract failed.', 'error');
            } finally {
                this.generating = false;
                this.generatingType = null;
            }
        },

        async generateSupplementaryAgreement() {
            if (this.generating || !this.selectedAgreementId || !contractId) return;

            this.generating = true;
            this.generatingType = 'agreement';
            this.showAgreementDialog = false;

            try {
                const response = await fetch(`/api/v1/documents/contracts/${contractId}/supplementary-agreements/${this.selectedAgreementId}/download`);
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.message || errorData.detail || 'Generate failed.');
                }

                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    const data = await response.json();
                    this.showToast(data.message || 'Supplementary agreement generated and saved.', 'success');
                } else {
                    await this.handleDownloadResponse(response, 'supplementary-agreement.docx');
                    this.showToast('Supplementary agreement generated.', 'success');
                }
            } catch (error) {
                console.error('generate supplementary agreement failed', error);
                this.showToast(error.message || 'Generate supplementary agreement failed.', 'error');
            } finally {
                this.generating = false;
                this.generatingType = null;
                this.selectedAgreementId = null;
            }
        },

        async generateFolder() {
            if (this.generating || !this.folderUnlocked || !contractId) return;

            this.generating = true;
            this.generatingType = 'folder';

            try {
                const response = await fetch(`/api/v1/documents/contracts/${contractId}/folder/download`);
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.message || errorData.detail || 'Generate failed.');
                }

                await this.handleDownloadResponse(response, 'contract-folder.zip');
                this.showToast('Folder generated.', 'success');
            } catch (error) {
                console.error('generate folder failed', error);
                this.showToast(error.message || 'Generate folder failed.', 'error');
            } finally {
                this.generating = false;
                this.generatingType = null;
                this.folderUnlocked = false;
            }
        },

        openAgreementDialog() {
            this.selectedAgreementId = null;
            this.showAgreementDialog = true;
        },

        closeAgreementDialog() {
            this.showAgreementDialog = false;
            this.selectedAgreementId = null;
        },

        selectAgreement(agreementId) {
            this.selectedAgreementId = agreementId;
        },

        async previewContract() {
            this.previewTitle = 'Contract Preview';
            this.previewRows = [];
            this.isLoadingPreview = true;
            this.showPreviewDialog = true;
            try {
                const resp = await fetch(`/api/v1/documents/contracts/${contractId}/preview`);
                const data = await resp.json();
                this.previewRows = data.data || [];
            } catch (err) {
                this.showToast('Preview load failed.', 'error');
            } finally {
                this.isLoadingPreview = false;
            }
        },

        openAgreementPreviewDialog() {
            this.previewAgreementId = null;
            this.showAgreementPreviewSelect = true;
        },

        async previewAgreement() {
            if (!this.previewAgreementId) return;
            this.showAgreementPreviewSelect = false;
            this.previewTitle = 'Supplementary Agreement Preview';
            this.previewRows = [];
            this.isLoadingPreview = true;
            this.showPreviewDialog = true;
            try {
                const resp = await fetch(`/api/v1/documents/contracts/${contractId}/supplementary-agreements/${this.previewAgreementId}/preview`);
                const data = await resp.json();
                this.previewRows = data.data || [];
            } catch (err) {
                this.showToast('Preview load failed.', 'error');
            } finally {
                this.isLoadingPreview = false;
            }
        },
    };
}

window.contractDetailApp = contractDetailApp;
