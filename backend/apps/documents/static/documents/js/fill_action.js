/**
 * fill_action.html 的 Alpine.js 组件注册
 * 通过 window.FILL_ACTION_CONFIG 获取模板渲染的配置
 */
(function () {
    function fillActionFactory() {
        var cfg = window.FILL_ACTION_CONFIG || {};
        var templateId = cfg.templateId;
        var serverCustomFields = cfg.customFields || [];

        return {
            caseId: '',
            caseQuery: '',
            caseResults: [],
            selectedCase: null,
            showDropdown: false,
            searchingCases: false,
            parties: [],
            selectedPartyIds: [],
            customFields: serverCustomFields,
            customValues: {},
            previewItems: [],
            results: {},
            step: 'input',
            loadingPreview: false,
            filling: false,
            partyError: '',

            init: function () {
                var self = this;
                this.customFields.forEach(function (f) {
                    self.customValues[f.mapping_id] = '';
                });
            },

            getCsrf: function () {
                var el = document.querySelector('[name=csrfmiddlewaretoken]');
                return el ? el.value : '';
            },

            searchCases: async function () {
                var q = this.caseQuery.trim();
                if (q.length < 1) { this.caseResults = []; this.showDropdown = false; return; }
                this.searchingCases = true;
                try {
                    var resp = await fetch('/api/v1/cases/search?q=' + encodeURIComponent(q) + '&limit=10', {
                        headers: { 'X-CSRFToken': this.getCsrf() }
                    });
                    if (resp.ok) {
                        this.caseResults = await resp.json();
                        this.showDropdown = this.caseResults.length > 0;
                    }
                } catch (e) {
                    this.caseResults = [];
                } finally {
                    this.searchingCases = false;
                }
            },

            selectCase: function (c) {
                this.selectedCase = c;
                this.caseId = c.id;
                this.caseQuery = c.name;
                this.showDropdown = false;
                this.partyError = '';
                this.step = 'input';
                this.parties = (c.parties || []).map(function (p) {
                    return {
                        id: p.id,
                        name: (p.client_detail && p.client_detail.name) || ('当事人' + p.id),
                        role: p.legal_status || ''
                    };
                });
                this.selectedPartyIds = [];
            },

            toggleParty: function (partyId) {
                var idx = this.selectedPartyIds.indexOf(partyId);
                if (idx === -1) { this.selectedPartyIds.push(partyId); }
                else { this.selectedPartyIds.splice(idx, 1); }
                this.step = 'input';
            },

            toggleAllParties: function (checked) {
                this.selectedPartyIds = checked ? this.parties.map(function (p) { return p.id; }) : [];
                this.step = 'input';
            },

            loadPreview: async function () {
                if (!this.caseId || this.selectedPartyIds.length === 0) return;
                this.loadingPreview = true;
                this.previewItems = [];
                try {
                    var partyId = this.selectedPartyIds[0];
                    var url = '/api/v1/documents/external-templates/' + templateId + '/preview/?case_id=' + this.caseId;
                    if (partyId) url += '&party_id=' + partyId;
                    var resp = await fetch(url, { headers: { 'X-CSRFToken': this.getCsrf() } });
                    if (!resp.ok) { this.partyError = window.FILL_ACTION_I18N && window.FILL_ACTION_I18N.previewFailed || '加载预览失败'; return; }
                    var data = await resp.json();
                    this.previewItems = data.fields || [];
                    var self = this;
                    this.previewItems.forEach(function (item) {
                        if (self.customValues[item.mapping_id]) {
                            item.fill_value = self.customValues[item.mapping_id];
                            item.value_source = 'manual';
                        }
                    });
                    this.step = 'preview';
                } catch (e) {
                    this.partyError = window.FILL_ACTION_I18N && window.FILL_ACTION_I18N.networkError || '网络错误，请重试';
                } finally {
                    this.loadingPreview = false;
                }
            },

            confirmFill: async function () {
                if (!this.caseId || this.selectedPartyIds.length === 0) return;
                this.filling = true;
                this.results = {};
                try {
                    var cv = {};
                    var self = this;
                    Object.keys(this.customValues).forEach(function (k) {
                        if (self.customValues[k]) cv[k] = self.customValues[k];
                    });
                    var body = {
                        template_ids: [templateId],
                        case_id: parseInt(this.caseId),
                        party_ids: this.selectedPartyIds,
                        custom_values: {}
                    };
                    if (Object.keys(cv).length > 0) body.custom_values[templateId] = cv;
                    var resp = await fetch('/api/v1/documents/external-templates/fill/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.getCsrf() },
                        body: JSON.stringify(body)
                    });
                    var data = await resp.json();
                    this.results = (resp.ok && data.success)
                        ? Object.assign({ success: true }, data)
                        : { error: data.message || (window.FILL_ACTION_I18N && window.FILL_ACTION_I18N.fillFailed) || '填充失败' };
                    this.step = 'result';
                } catch (e) {
                    this.results = { error: (window.FILL_ACTION_I18N && window.FILL_ACTION_I18N.networkError) || '网络错误，请重试' };
                    this.step = 'result';
                } finally {
                    this.filling = false;
                }
            }
        };
    }

    // Alpine v3: 用 alpine:init 注册，确保在 Alpine 初始化前注册好
    document.addEventListener('alpine:init', function () {
        Alpine.data('fillAction', fillActionFactory);
    });
}());
