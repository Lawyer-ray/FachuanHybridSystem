/**
 * 模拟庭审 Alpine.js 组件
 */
function mockTrialApp(config = {}) {
    return {
        caseId: config.caseId || null,
        caseName: config.caseName || '',
        sessionId: null,
        sessions: [],
        messages: [],
        inputMessage: '',
        loading: false,
        selectedMode: null,
        ws: null,
        statusText: '',
        // 进度条相关
        progress: {
            show: false,
            current: 0,
            total: 0,
            percentage: 0,
            message: ''
        },
        // 批量处理
        batchMode: false,
        // 导出
        exporting: false,
        // 错误重试
        lastError: null,
        retryCount: 0,
        maxRetries: 3,
        // 辩论难度
        debateDifficulty: 'medium',
        showDifficultySelector: false,

        async init() {
            await this.loadSessions();
        },

        // ========== 会话管理 ==========
        async loadSessions() {
            try {
                const resp = await fetch(`/api/v1/mock-trial/sessions?case_id=${this.caseId}`, { credentials: 'include' });
                if (!resp.ok) return;
                const data = await resp.json();
                this.sessions = (data.results || []).sort((a, b) =>
                    Date.parse(b.updated_at || b.created_at || '') - Date.parse(a.updated_at || a.created_at || '')
                );
            } catch (e) { console.error('加载会话失败:', e); }
        },

        async selectMode(mode) {
            if (this.sessionId) return;
            this.selectedMode = mode;
            // 辩论模式显示难度选择
            if (mode === 'debate') {
                this.showDifficultySelector = true;
            }
            this.loading = true;
            try {
                const resp = await fetch('/api/v1/mock-trial/sessions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.getCsrfToken() },
                    credentials: 'include',
                    body: JSON.stringify({ case_id: this.caseId })
                });
                if (!resp.ok) throw new Error('创建会话失败');
                const data = await resp.json();
                this.sessionId = data.session_id;
                this.statusText = '进行中';
                this.connectWebSocket(data.session_id);
                // 发送难度设置
                if (mode === 'debate') {
                    this.ws.onopen = () => {
                        this.ws.send(JSON.stringify({
                            type: 'set_difficulty',
                            difficulty: this.debateDifficulty
                        }));
                    };
                }
                await this.loadSessions();
            } catch (e) {
                console.error(e);
                this.loading = false;
            }
        },

        async loadSession(sessionId) {
            if (this.ws) { this.ws.close(); this.ws = null; }
            this.sessionId = sessionId;
            this.messages = [];
            this.loading = true;
            this.resetProgress();
            try {
                const resp = await fetch(`/api/v1/mock-trial/sessions/${sessionId}`, { credentials: 'include' });
                if (!resp.ok) return;
                const data = await resp.json();
                this.messages = data.messages || [];
                this.selectedMode = (data.metadata || {}).mock_trial_mode || null;
                this.statusText = data.status === 'active' ? '进行中' : '已完成';
                this.$nextTick(() => this.scrollToBottom());
                // 如果会话还在进行中，连接 WebSocket
                if (data.status === 'active') {
                    this.connectWebSocket(sessionId);
                }
            } catch (e) { console.error(e); }
            this.loading = false;
        },

        async deleteSession(sessionId) {
            try {
                await fetch(`/api/v1/mock-trial/sessions/${sessionId}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': this.getCsrfToken() },
                    credentials: 'include'
                });
                if (sessionId === this.sessionId) {
                    this.sessionId = null;
                    this.messages = [];
                    this.selectedMode = null;
                    this.resetProgress();
                    if (this.ws) { this.ws.close(); this.ws = null; }
                }
                await this.loadSessions();
            } catch (e) { console.error(e); }
        },

        // ========== 导出报告 ==========
        async exportReport() {
            if (!this.sessionId || this.exporting) return;
            this.exporting = true;
            try {
                const resp = await fetch(`/api/v1/mock-trial/sessions/${this.sessionId}/export`, {
                    credentials: 'include'
                });
                if (!resp.ok) throw new Error('导出失败');

                // 下载文件
                const blob = await resp.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `模拟庭审报告_${this.caseName}.docx`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } catch (e) {
                console.error('导出失败:', e);
                alert('导出失败，请重试');
            }
            this.exporting = false;
        },

        // ========== WebSocket ==========
        connectWebSocket(sessionId) {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const url = `${protocol}//${location.host}/ws/mock-trial/sessions/${sessionId}/`;
            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                this.loading = false;
                this.retryCount = 0;
            };
            this.ws.onmessage = (e) => this.handleWsMessage(JSON.parse(e.data));
            this.ws.onerror = (e) => {
                console.error('WS error:', e);
                this.loading = false;
                this.lastError = e;
            };
            this.ws.onclose = () => {
                this.loading = false;
                // 自动重连
                if (this.retryCount < this.maxRetries && this.sessionId) {
                    this.retryCount++;
                    setTimeout(() => {
                        if (this.sessionId) this.connectWebSocket(this.sessionId);
                    }, 2000 * this.retryCount);
                }
            };
        },

        handleWsMessage(data) {
            switch (data.type) {
                case 'system_message':
                    this.messages.push({ role: 'system', content: data.content, created_at: new Date().toISOString(), metadata: data.metadata || {} });
                    break;
                case 'assistant_complete':
                    this.messages.push({ role: 'assistant', content: data.content, created_at: new Date().toISOString(), metadata: data.metadata || {} });
                    break;
                case 'error':
                    this.messages.push({ role: 'system', content: `❌ ${data.message}`, created_at: new Date().toISOString() });
                    break;
                case 'progress':
                    this.updateProgress(data.current, data.total, data.percentage, data.message);
                    break;
            }
            this.loading = false;
            this.$nextTick(() => this.scrollToBottom());
        },

        sendMessage() {
            if (!this.inputMessage.trim() || !this.ws || this.loading) return;
            this.messages.push({ role: 'user', content: this.inputMessage, created_at: new Date().toISOString() });
            this.ws.send(JSON.stringify({ type: 'user_message', content: this.inputMessage }));
            this.inputMessage = '';
            this.loading = true;
            this.$nextTick(() => this.scrollToBottom());
        },

        // ========== 批量处理 ==========
        startBatchMode() {
            this.batchMode = true;
            this.ws.send(JSON.stringify({ type: 'start_batch' }));
        },

        stopBatchMode() {
            this.batchMode = false;
        },

        // ========== 进度条 ==========
        updateProgress(current, total, percentage, message) {
            this.progress = {
                show: true,
                current: current || 0,
                total: total || 0,
                percentage: percentage || 0,
                message: message || `处理中 ${current}/${total}`
            };
            // 完成时隐藏
            if (current >= total && total > 0) {
                setTimeout(() => this.resetProgress(), 2000);
            }
        },

        resetProgress() {
            this.progress = {
                show: false,
                current: 0,
                total: 0,
                percentage: 0,
                message: ''
            };
        },

        // ========== 工具方法 ==========
        scrollToBottom() {
            const el = this.$refs.messagesContainer;
            if (el) el.scrollTop = el.scrollHeight;
        },

        renderMarkdown(text) {
            if (!text) return '';
            // 使用更完善的 markdown 渲染
            if (typeof marked !== 'undefined') {
                return marked.parse(text);
            }
            // 降级到简单渲染
            return text
                .replace(/^### (.+)$/gm, '<h4>$1</h4>')
                .replace(/^## (.+)$/gm, '<h3>$1</h3>')
                .replace(/^# (.+)$/gm, '<h2>$1</h2>')
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/^- (.+)$/gm, '<li>$1</li>')
                .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
                .replace(/\n/g, '<br>');
        },

        getModeLabel(mode) {
            return { judge: '🔍 法官视角', cross_exam: '📋 质证模拟', debate: '💬 辩论模拟' }[mode] || mode || '';
        },

        getSessionPreview(session) {
            // 获取会话预览文本
            const messages = session.messages || [];
            const lastMsg = messages[messages.length - 1];
            if (lastMsg) {
                return lastMsg.content.substring(0, 50) + (lastMsg.content.length > 50 ? '...' : '');
            }
            return '暂无消息';
        },

        formatTime(dateStr) {
            if (!dateStr) return '';
            const d = new Date(dateStr);
            return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
        },

        formatMsgTime(dateStr) {
            if (!dateStr) return '';
            const d = new Date(dateStr);
            return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
        },

        getCsrfToken() {
            const el = document.querySelector('[name=csrfmiddlewaretoken]');
            if (el) return el.value;
            const match = document.cookie.match(/csrftoken=([^;]+)/);
            return match ? match[1] : '';
        }
    };
}
