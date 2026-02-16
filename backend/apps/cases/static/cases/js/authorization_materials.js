function authorizationMaterialsApp(config = {}) {
    return {
        apiBasePath: config.apiBasePath || '/api/v1/documents',
        caseId: config.caseId || null,
        legalEntitiesJson: typeof config.legalEntitiesJson === 'string' ? config.legalEntitiesJson : '',
        legalEntities: [],
        ourPartiesJson: typeof config.ourPartiesJson === 'string' ? config.ourPartiesJson : '',
        ourParties: [],

        isEntityDialogOpen: false,
        isPoaDialogOpen: false,
        isDownloading: false,
        selectedEntityIds: [],
        selectedOurPartyIds: [],
        poaMode: '',
        errorMessage: '',
        successMessage: '',

        get hasLegalEntities() {
            return Array.isArray(this.legalEntities) && this.legalEntities.length > 0;
        },

        get hasOurParties() {
            return Array.isArray(this.ourParties) && this.ourParties.length > 0;
        },

        init() {
            this.legalEntities = this._parseLegalEntities();
            this.ourParties = this._parseOurParties();
            if (!this._boundKeyDownHandler) {
                this._boundKeyDownHandler = this.handleKeyDown.bind(this);
            }
            this.$watch('isEntityDialogOpen', () => this._syncKeyDownListener());
            this.$watch('isPoaDialogOpen', () => this._syncKeyDownListener());
            this._syncKeyDownListener();
        },

        _syncKeyDownListener() {
            const shouldBind = (this.isEntityDialogOpen || this.isPoaDialogOpen) && !this.isDownloading;
            if (shouldBind) {
                document.addEventListener('keydown', this._boundKeyDownHandler);
            } else {
                document.removeEventListener('keydown', this._boundKeyDownHandler);
            }
        },

        _parseLegalEntities() {
            if (!this.legalEntitiesJson) return [];
            try {
                const parsed = JSON.parse(this.legalEntitiesJson);
                if (Array.isArray(parsed)) return parsed;
                return [];
            } catch {
                return [];
            }
        },

        _parseOurParties() {
            if (!this.ourPartiesJson) return [];
            try {
                const parsed = JSON.parse(this.ourPartiesJson);
                if (Array.isArray(parsed)) return parsed;
                return [];
            } catch {
                return [];
            }
        },

        handleKeyDown(e) {
            if (e.key === 'Escape' && this.isEntityDialogOpen && !this.isDownloading) {
                this.closeEntityDialog();
            }
            if (e.key === 'Escape' && this.isPoaDialogOpen && !this.isDownloading) {
                this.closePoaDialog();
            }
        },

        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        extractFilename(response) {
            const disposition = response.headers.get('content-disposition');
            if (!disposition) return null;

            const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/i);
            if (utf8Match) {
                return decodeURIComponent(utf8Match[1]);
            }

            const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match) {
                return match[1].replace(/['"]/g, '');
            }

            return null;
        },

        downloadBlob(blob, filename) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        },

        async fetchAndDownload(url, { defaultFilename = 'download.docx', body = null } = {}) {
            const requestInit = {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                }
            };
            if (body !== null && body !== undefined) {
                requestInit.body = JSON.stringify(body);
            }
            const response = await fetch(url, {
                ...requestInit
            });

            if (!response.ok) {
                let errorData;
                try {
                    errorData = await response.json();
                } catch {
                    errorData = { message: '生成失败' };
                }
                const message = this._extractErrorMessage(errorData) || '生成失败';
                throw new Error(message);
            }

            const contentType = response.headers.get('content-type');
            if (contentType?.includes('application/json')) {
                const data = await response.json();
                return { type: 'json', data };
            }

            const blob = await response.blob();
            const filename = this.extractFilename(response) || defaultFilename;
            this.downloadBlob(blob, filename);
            return { type: 'file', filename };
        },

        _extractErrorMessage(errorData) {
            if (!errorData) return '';
            if (typeof errorData === 'string') return errorData;
            if (typeof errorData.message === 'string' && errorData.message) return errorData.message;
            if (typeof errorData.detail === 'string' && errorData.detail) return errorData.detail;
            if (Array.isArray(errorData.detail)) {
                const msgs = errorData.detail
                    .map((x) => x?.msg || x?.message || '')
                    .filter(Boolean);
                if (msgs.length) return msgs.join('；');
            }
            if (typeof errorData.error === 'string' && errorData.error) return errorData.error;
            return '';
        },

        showSuccess(message) {
            this.successMessage = message;
            setTimeout(() => {
                this.successMessage = '';
            }, 3000);
        },

        showError(message) {
            this.errorMessage = message;
        },

        handleOverlayClick(e) {
            if (e.target === e.currentTarget && !this.isDownloading) {
                this.closeEntityDialog();
                this.closePoaDialog();
            }
        },

        openEntityDialog() {
            if (this.isDownloading) return;
            this.isEntityDialogOpen = true;
            this.selectedEntityIds = [];
            this.errorMessage = '';
        },

        closeEntityDialog() {
            if (this.isDownloading) return;
            this.isEntityDialogOpen = false;
            this.selectedEntityIds = [];
            this.errorMessage = '';
        },

        toggleAllEntities(e) {
            if (!e?.target) return;
            if (e.target.checked) {
                this.selectedEntityIds = this.legalEntities.map((x) => x.id);
            } else {
                this.selectedEntityIds = [];
            }
        },

        isAllSelected() {
            return this.hasLegalEntities && this.selectedEntityIds.length === this.legalEntities.length;
        },

        async handleLegalRepCertificateClick() {
            if (!this.hasLegalEntities) {
                return;
            }

            if (this.legalEntities.length === 1) {
                const only = this.legalEntities[0];
                await this.downloadLegalRepCertificate(only.id);
                return;
            }

            this.openEntityDialog();
        },

        openPoaDialog() {
            if (this.isDownloading) return;
            this.isPoaDialogOpen = true;
            this.poaMode = 'individual';
            this.errorMessage = '';
            this.selectedOurPartyIds = [];
        },

        closePoaDialog() {
            if (this.isDownloading) return;
            this.isPoaDialogOpen = false;
            this.poaMode = '';
            this.errorMessage = '';
            this.selectedOurPartyIds = [];
        },

        selectPoaMode(mode) {
            if (this.isDownloading) return;
            this.poaMode = mode;
            if (mode === 'combined') {
                this.selectedOurPartyIds = [];
            }
        },

        async confirmPowerOfAttorney() {
            if (!this.poaMode) return;
            if (this.poaMode === 'combined') {
                const ok = await this.downloadPowerOfAttorneyCombined();
                if (ok) this.closePoaDialog();
                return;
            }
            if (!this.selectedOurPartyIds.length) {
                this.errorMessage = '请选择我方当事人';
                return;
            }
            const ok = await this.downloadSelectedPowerOfAttorneys();
            if (ok) this.closePoaDialog();
        },

        toggleAllOurParties(e) {
            if (!e?.target) return;
            if (e.target.checked) {
                this.selectedOurPartyIds = this.ourParties.map((x) => x.id);
            } else {
                this.selectedOurPartyIds = [];
            }
        },

        isAllOurPartiesSelected() {
            return this.hasOurParties && this.selectedOurPartyIds.length === this.ourParties.length;
        },

        async handlePowerOfAttorneyClick() {
            if (!this.hasOurParties) return;
            if (this.ourParties.length === 1) {
                await this.downloadPowerOfAttorney(this.ourParties[0].id);
                return;
            }
            this.openPoaDialog();
        },

        async downloadAuthorityLetter() {
            if (!this.caseId) return;
            this.isDownloading = true;
            this.errorMessage = '';

            try {
                const result = await this.fetchAndDownload(
                    `${this.apiBasePath}/cases/${this.caseId}/authorization/letter/download`,
                    { defaultFilename: '所函.docx' }
                );

                if (result.type === 'json') {
                    this.showSuccess(result.data?.message || '所函生成成功');
                } else {
                    this.showSuccess('所函生成成功，正在下载...');
                }
            } catch (error) {
                this.showError(error.message || '所函生成失败');
            } finally {
                this.isDownloading = false;
            }
        },

        async downloadFullAuthorizationPackage() {
            if (!this.caseId) return;
            if (!this.hasOurParties) return;

            this.isDownloading = true;
            this.errorMessage = '';

            try {
                await this.fetchAndDownload(
                    `${this.apiBasePath}/cases/${this.caseId}/authorization/package/download`,
                    { defaultFilename: '全套授权委托材料.zip' }
                );
                this.showSuccess('全套委托材料生成成功，正在下载...');
            } catch (error) {
                this.showError(error.message || '全套委托材料生成失败');
            } finally {
                this.isDownloading = false;
            }
        },

        async downloadPowerOfAttorney(clientId, { silent = false } = {}) {
            if (!this.caseId || !clientId) return;
            this.isDownloading = true;
            if (!silent) this.errorMessage = '';

            try {
                await this.fetchAndDownload(
                    `${this.apiBasePath}/cases/${this.caseId}/authorization/power-of-attorney/${clientId}/download`,
                    { defaultFilename: '授权委托书.docx' }
                );
                if (!silent) {
                    this.showSuccess('授权委托书生成成功，正在下载...');
                }
            } catch (error) {
                if (!silent) {
                    this.showError(error.message || '授权委托书生成失败');
                } else {
                    throw error;
                }
            } finally {
                this.isDownloading = false;
            }
        },

        async downloadPowerOfAttorneyCombined() {
            if (!this.caseId) return;
            this.isDownloading = true;
            this.errorMessage = '';

            try {
                const result = await this.fetchAndDownload(
                    `${this.apiBasePath}/cases/${this.caseId}/authorization/power-of-attorney/combined/download`,
                    {
                        defaultFilename: '授权委托书.docx',
                        body: { client_ids: this.ourParties.map((x) => x.id) }
                    }
                );
                if (result?.type === 'json') {
                    throw new Error(result.data?.message || '生成失败');
                }
                this.showSuccess('授权委托书生成成功，正在下载...');
                return true;
            } catch (error) {
                this.showError(error.message || '授权委托书生成失败');
                return false;
            } finally {
                this.isDownloading = false;
            }
        },

        async downloadSelectedPowerOfAttorneys() {
            if (!this.caseId) return;
            this.isDownloading = true;
            this.errorMessage = '';

            try {
                for (const clientId of this.selectedOurPartyIds) {
                    await this.fetchAndDownload(
                        `${this.apiBasePath}/cases/${this.caseId}/authorization/power-of-attorney/${clientId}/download`,
                        { defaultFilename: '授权委托书.docx' }
                    );
                }
                this.showSuccess('授权委托书生成成功，正在下载...');
                return true;
            } catch (error) {
                this.errorMessage = error.message || '授权委托书生成失败';
                return false;
            } finally {
                this.isDownloading = false;
            }
        },

        async downloadLegalRepCertificate(clientId, { silent = false } = {}) {
            if (!this.caseId || !clientId) return;
            this.isDownloading = true;
            if (!silent) this.errorMessage = '';

            try {
                await this.fetchAndDownload(
                    `${this.apiBasePath}/cases/${this.caseId}/authorization/legal-rep-certificate/${clientId}/download`,
                    { defaultFilename: '法定代表人身份证明书.docx' }
                );
                if (!silent) {
                    this.showSuccess('身份证明书生成成功，正在下载...');
                }
            } catch (error) {
                if (!silent) {
                    this.showError(error.message || '身份证明书生成失败');
                } else {
                    throw error;
                }
            } finally {
                this.isDownloading = false;
            }
        },

        async downloadSelectedLegalRepCertificates() {
            if (!this.caseId) return;
            if (!this.selectedEntityIds.length) {
                this.errorMessage = '请选择法人';
                return;
            }

            this.isDownloading = true;
            this.errorMessage = '';

            try {
                for (const clientId of this.selectedEntityIds) {
                    await this.fetchAndDownload(
                        `${this.apiBasePath}/cases/${this.caseId}/authorization/legal-rep-certificate/${clientId}/download`,
                        { defaultFilename: '法定代表人身份证明书.docx' }
                    );
                }
                this.closeEntityDialog();
                this.showSuccess('身份证明书生成成功，正在下载...');
            } catch (error) {
                this.errorMessage = error.message || '身份证明书生成失败';
            } finally {
                this.isDownloading = false;
            }
        },
    };
}

window.authorizationMaterialsApp = authorizationMaterialsApp;
