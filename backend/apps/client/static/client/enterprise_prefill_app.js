function enterprisePrefillApp() {
    return {
        provider: 'tianyancha',
        keyword: '',
        isSearching: false,
        isLoadingPrefill: false,
        searchError: '',
        prefillError: '',
        applyMessage: '',
        companies: [],
        selectedCompany: null,
        profile: null,
        prefill: null,
        existingClient: null,
        applyMode: 'fill_empty',

        init() {
            this.provider = 'tianyancha';
        },

        async searchCompanies() {
            const normalizedKeyword = String(this.keyword || '').trim();
            if (!normalizedKeyword) {
                this.searchError = '请输入企业名称关键词';
                return;
            }

            this.isSearching = true;
            this.searchError = '';
            this.prefillError = '';
            this.applyMessage = '';
            this.selectedCompany = null;
            this.profile = null;
            this.prefill = null;
            this.existingClient = null;

            try {
                const params = new URLSearchParams({
                    keyword: normalizedKeyword,
                    provider: this.provider,
                    limit: '8',
                });
                const payload = await this.fetchJson('/api/v1/client/clients/enterprise/search?' + params.toString());
                this.companies = Array.isArray(payload.items) ? payload.items : [];
                if (!this.companies.length) {
                    this.searchError = '暂未检索到匹配企业，可换关键词继续搜索，或直接手工填写';
                }
            } catch (error) {
                this.searchError = error instanceof Error ? error.message : '企业搜索失败';
                this.companies = [];
            } finally {
                this.isSearching = false;
            }
        },

        async selectCompany(company) {
            if (!company || !company.company_id) {
                return;
            }

            this.selectedCompany = company;
            this.isLoadingPrefill = true;
            this.prefillError = '';
            this.applyMessage = '';
            this.profile = null;
            this.prefill = null;
            this.existingClient = null;

            try {
                const params = new URLSearchParams({
                    company_id: String(company.company_id),
                    provider: this.provider,
                });
                const payload = await this.fetchJson('/api/v1/client/clients/enterprise/prefill?' + params.toString());
                this.profile = payload.profile || null;
                this.prefill = payload.prefill || null;
                this.existingClient = payload.existing_client || null;
            } catch (error) {
                this.prefillError = error instanceof Error ? error.message : '企业详情加载失败';
            } finally {
                this.isLoadingPrefill = false;
            }
        },

        applyToForm() {
            if (!this.prefill) {
                this.prefillError = '请先选择企业并加载详情';
                return;
            }

            const fields = [
                ['client_type', this.prefill.client_type],
                ['name', this.prefill.name],
                ['id_number', this.prefill.id_number],
                ['legal_representative', this.prefill.legal_representative],
                ['address', this.prefill.address],
                ['phone', this.prefill.phone],
            ];

            fields.forEach(([fieldName, value]) => {
                if (value === undefined || value === null) {
                    return;
                }

                const field = document.getElementById('id_' + fieldName);
                if (!field) {
                    return;
                }

                const normalizedValue = String(value);
                if (!normalizedValue.trim() && fieldName !== 'phone') {
                    return;
                }

                if (this.applyMode === 'fill_empty' && this.hasFieldValue(field)) {
                    return;
                }

                if (field.type === 'checkbox') {
                    field.checked = normalizedValue === 'true';
                } else {
                    field.value = normalizedValue;
                }
                field.dispatchEvent(new Event('change'));
                this.highlightField(field);
            });

            this.applyMessage = this.applyMode === 'overwrite' ? '已覆盖写入企业信息' : '已填充空白字段';
            setTimeout(() => {
                this.applyMessage = '';
            }, 3000);
        },

        hasFieldValue(field) {
            if (field.type === 'checkbox') {
                return field.checked;
            }
            return String(field.value || '').trim() !== '';
        },

        highlightField(field) {
            field.classList.add('enterprise-prefill-highlight');
            setTimeout(() => {
                field.classList.remove('enterprise-prefill-highlight');
            }, 2500);
        },

        existingClientUrl() {
            if (!this.existingClient || !this.existingClient.id) {
                return '';
            }
            return '/admin/client/client/' + this.existingClient.id + '/change/';
        },

        async fetchJson(url) {
            const response = await fetch(url, { credentials: 'same-origin' });
            let payload = {};
            try {
                payload = await response.json();
            } catch (error) {
                payload = {};
            }

            if (!response.ok) {
                const message = this.extractErrorMessage(payload);
                throw new Error(message || '请求失败');
            }
            return payload;
        },

        extractErrorMessage(payload) {
            if (!payload || typeof payload !== 'object') {
                return '';
            }
            if (typeof payload.message === 'string' && payload.message.trim()) {
                return payload.message.trim();
            }
            if (typeof payload.detail === 'string' && payload.detail.trim()) {
                return payload.detail.trim();
            }
            if (payload.detail && typeof payload.detail === 'object' && typeof payload.detail.message === 'string') {
                return String(payload.detail.message).trim();
            }
            return '';
        },
    };
}
