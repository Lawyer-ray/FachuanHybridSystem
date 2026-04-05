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
        providerStatuses: {},
        statusHint: '',
        isProviderReady: true,
        systemConfigUrl: 'http://127.0.0.1:8002/admin/core/systemconfig/',

        async init() {
            this.provider = 'tianyancha';
            await this.loadProviderStatuses();
            this.applyProviderAvailability();
        },

        onProviderChange() {
            this.searchError = '';
            this.prefillError = '';
            this.applyMessage = '';
            this.companies = [];
            this.selectedCompany = null;
            this.profile = null;
            this.prefill = null;
            this.existingClient = null;
            this.applyProviderAvailability();
        },

        async loadProviderStatuses() {
            try {
                const payload = await this.fetchJson('/api/v1/enterprise-data/providers?include_tools=true');
                const items = Array.isArray(payload.items) ? payload.items : [];
                this.providerStatuses = items.reduce((acc, item) => {
                    const name = String(item && item.name ? item.name : '').trim();
                    if (name) {
                        acc[name] = item;
                    }
                    return acc;
                }, {});
            } catch (error) {
                this.providerStatuses = {};
            }
        },

        applyProviderAvailability() {
            const item = this.providerStatuses[this.provider] || null;
            const unavailableReason = this.getProviderUnavailableReason(item);
            this.isProviderReady = !unavailableReason;
            this.statusHint = unavailableReason;
            if (!this.isProviderReady) {
                this.searchError = '';
            }
        },

        getProviderUnavailableReason(providerItem) {
            if (!providerItem || typeof providerItem !== 'object') {
                return '企业信息查询服务状态未知，请稍后重试';
            }

            const providerName = String(providerItem.name || '').trim();
            const providerEnabled = providerItem.enabled !== false;
            const providerNote = String(providerItem.note || '').trim();
            const normalizedNote = providerNote.toLowerCase();
            const isTianyancha = providerName === 'tianyancha';

            if (!providerEnabled) {
                return isTianyancha
                    ? '天眼查企业查询功能未启用，请在系统配置中开启并填写 TIANYANCHA_MCP_API_KEY'
                    : '当前企业查询服务未启用';
            }

            if (
                normalizedNote.includes('api key 未配置') ||
                normalizedNote.includes('api key') && normalizedNote.includes('未配置') ||
                normalizedNote.includes('mcp api key 未配置')
            ) {
                return isTianyancha
                    ? '未检测到 TIANYANCHA_MCP_API_KEY，企业查询功能已禁用，请先到系统配置填写'
                    : '当前服务 API Key 未配置，请先完善系统配置';
            }

            if (normalizedNote.includes('骨架实现') || normalizedNote.includes('尚未完成')) {
                return '当前服务尚未开放，请切换到可用服务';
            }

            return '';
        },

        async searchCompanies() {
            if (!this.isProviderReady) {
                this.searchError = this.statusHint || '企业查询功能当前不可用';
                return;
            }

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
                this.searchError = this.resolveEnterpriseError(error, '企业搜索失败');
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
                this.applyToForm();
            } catch (error) {
                this.prefillError = this.resolveEnterpriseError(error, '企业详情加载失败');
            } finally {
                this.isLoadingPrefill = false;
            }
        },

        resolveEnterpriseError(error, fallbackMessage) {
            const message = error instanceof Error ? error.message : '';
            const errorCode = error && typeof error === 'object' && typeof error.code === 'string'
                ? error.code
                : '';
            const errorDetails = error && typeof error === 'object' && error.errors && typeof error.errors === 'object'
                ? error.errors
                : {};
            const detailText = [
                String(message || '').toLowerCase(),
                String(errorCode || '').toLowerCase(),
                String(errorDetails.provider || '').toLowerCase(),
                String(errorDetails.detail || '').toLowerCase(),
            ].join(' ');

            const shouldGuideConfig =
                errorCode === 'PROVIDER_API_KEY_MISSING' ||
                errorCode === 'MCP_API_KEY_MISSING' ||
                errorCode === 'MCP_AUTH_ERROR' ||
                (errorCode === 'MCP_HTTP_ERROR' && Number(errorDetails.status_code || 0) === 500 && this.provider === 'tianyancha') ||
                detailText.includes('api key') ||
                detailText.includes('鉴权') ||
                detailText.includes('auth');

            if (shouldGuideConfig) {
                this.isProviderReady = false;
                this.statusHint = '天眼查鉴权异常，请到系统配置更换 TIANYANCHA_MCP_API_KEY 后重试';
                return '';
            }

            return message || fallbackMessage;
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
                if (!normalizedValue.trim()) {
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

            this.applyMessage = '已自动填充企业信息，可直接保存或继续编辑';
            setTimeout(() => {
                this.applyMessage = '';
            }, 3000);
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
                const requestError = new Error(message || '请求失败');
                requestError.code = payload && typeof payload.code === 'string' ? payload.code : '';
                requestError.errors = payload && payload.errors && typeof payload.errors === 'object' ? payload.errors : {};
                requestError.status = Number(response.status || 0);
                throw requestError;
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
