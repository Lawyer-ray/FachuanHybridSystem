/**
 * JTN OA 立案 - 金诚同达OA立案独立逻辑
 * 
 * 从 filing.html 解耦，作为律所特定OA立案模块。
 * 未来换律所时，替换为对应律所的OA立案JS文件即可。
 */
function jtnOaFilingApp(config = {}) {
    return {
        contractId: config.contractId,
        caseId: config.caseId || null,
        configs: [],
        loading: false,
        executing: false,
        selectedConfigId: '',
        lastResult: null,

        async init() {
            await this.loadConfigs();
        },

        async loadConfigs() {
            this.loading = true;
            try {
                const resp = await fetch('/api/v1/oa-filing/configs');
                if (resp.ok) this.configs = await resp.json();
            } catch (e) {
                console.error('loadConfigs error:', e);
            } finally {
                this.loading = false;
            }
        },

        hasCredential() {
            const cfg = this.configs.find(c => c.id == this.selectedConfigId);
            return cfg ? cfg.has_credential : false;
        },

        async executeFiling() {
            if (!this.selectedConfigId) return;
            this.executing = true;
            this.lastResult = null;
            try {
                const body = {
                    site_name: this.selectedConfigId,
                    contract_id: this.contractId,
                };
                if (this.caseId) body.case_id = this.caseId;
                const resp = await fetch('/api/v1/oa-filing/execute', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify(body)
                });
                const data = await resp.json();
                if (resp.ok && data.id) {
                    this.lastResult = data;
                    this.pollSession(data.id);
                } else {
                    this.lastResult = {status: 'failed', error_message: data.detail || '请求失败'};
                    this.executing = false;
                }
            } catch (e) {
                console.error('executeFiling error:', e);
                this.executing = false;
            }
        },

        async pollSession(sessionId) {
            const poll = async () => {
                try {
                    const resp = await fetch(`/api/v1/oa-filing/session/${sessionId}`);
                    if (resp.ok) {
                        const data = await resp.json();
                        this.lastResult = data;
                        if (data.status === 'in_progress') {
                            setTimeout(poll, 3000);
                            return;
                        }
                    }
                } catch (e) {
                    console.error('pollSession error:', e);
                }
                this.executing = false;
            };
            setTimeout(poll, 3000);
        },

        getCsrfToken() {
            const name = 'csrftoken';
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        }
    };
}

window.jtnOaFilingApp = jtnOaFilingApp;
