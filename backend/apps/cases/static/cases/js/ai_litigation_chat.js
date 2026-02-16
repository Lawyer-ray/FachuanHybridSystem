/**
 * AI 诉讼文书生成 - 对话界面（标签页版本）
 *
 * 使用 Alpine.js 管理状态和交互
 */

function aiLitigationTabApp(config = {}) {
    return {
        // ========== 状态 ==========
        sessions: [],              // 会话列表
        currentSessionId: null,    // 当前会话ID
        messages: [],              // 当前会话的消息列表
        ws: null,                  // WebSocket 连接
        loading: false,            // 加载状态
        sending: false,            // 发送中状态
        showDeleteConfirm: false,  // 删除确认对话框
        sessionToDelete: null,     // 待删除的会话ID
        inputMessage: '',          // 输入框内容
        caseId: null,

        // ========== 生命周期 ==========
        async init() {
            this.caseId = config.caseId || window.CASE_ID;
            await this.loadSessions();
            if (this.sessions.length > 0) {
                await this.selectSession(this.sessions[0].session_id);
            }
            this.focusInput();
        },

        focusInput() {
            this.$nextTick(() => {
                const el = (this.$refs && this.$refs.inputArea) || (this.$el ? this.$el.querySelector('textarea') : null);
                if (el && !el.disabled) {
                    el.focus();
                }
            });
        },

        // ========== 会话管理 ==========
        async loadSessions() {
            try {
                const response = await fetch(
                    `/api/v1/litigation/sessions?case_id=${this.caseId}`,
                    {
                        credentials: 'include'  // 包含 cookies（session）
                    }
                );

                if (!response.ok) {
                    throw new Error('加载会话列表失败');
                }

                const data = await response.json();
                const list = (data.results || data.sessions || []).map(s => ({
                    session_id: s.session_id,
                    case_id: s.case_id,
                    document_type: s.document_type || '',
                    status: s.status || 'active',
                    metadata: s.metadata || {},
                    created_at: s.created_at,
                    updated_at: s.updated_at,
                    message_count: s.message_count ?? 0,
                }));
                // 按更新时间倒序
                list.sort((a, b) => {
                    const at = Date.parse(a.updated_at || a.created_at || '') || 0;
                    const bt = Date.parse(b.updated_at || b.created_at || '') || 0;
                    return bt - at;
                });
                this.sessions = list;
            } catch (error) {
                console.error('加载会话列表失败:', error);
            }
        },

        async selectSession(sessionId) {
            if (this.currentSessionId === sessionId) return;

            this.currentSessionId = sessionId;
            this.messages = [];

            // 断开旧连接
            if (this.ws) {
                this.ws.close();
                this.ws = null;
            }

            // 加载历史消息
            await this.loadMessages(sessionId);

            // 连接 WebSocket
            this.connectWebSocket(sessionId);
            this.focusInput();
        },

        async createNewSession() {
            try {
                const response = await fetch('/api/v1/litigation/sessions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    credentials: 'include',  // 包含 cookies
                    body: JSON.stringify({ case_id: this.caseId })
                });

                if (!response.ok) {
                    throw new Error('创建会话失败');
                }

                const data = await response.json();
                await this.loadSessions();
                await this.selectSession(data.session_id);
            } catch (error) {
                console.error('创建会话失败:', error);
            }
        },

        async deleteSession(sessionId) {
            if (!sessionId) return;
            try {
                const response = await fetch(`/api/v1/litigation/sessions/${sessionId}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': this.getCsrfToken() },
                    credentials: 'include'
                });

                if (response.status !== 204 && !response.ok) {
                    throw new Error('删除会话失败');
                }

                await this.loadSessions();

                // 如果删除的是当前会话，切换到第一个会话
                if (sessionId === this.currentSessionId) {
                    if (this.sessions.length > 0) {
                        await this.selectSession(this.sessions[0].session_id);
                    } else {
                        this.currentSessionId = null;
                        this.messages = [];
                    }
                }
            } catch (error) {
                console.error('删除会话失败:', error);
            }
        },

        // ========== 消息管理 ==========
        async loadMessages(sessionId) {
            this.loading = true;
            try {
                const response = await fetch(
                    `/api/v1/litigation/sessions/${sessionId}/messages`
                );

                if (!response.ok) {
                    throw new Error('加载消息失败');
                }

                const data = await response.json();
                this.messages = data.messages || [];
                this.$nextTick(() => {
                    this.scrollToBottom();
                });
                this.focusInput();
            } catch (error) {
                console.error('加载消息失败:', error);
            } finally {
                this.loading = false;
            }
        },

        // ========== WebSocket ==========
        connectWebSocket(sessionId) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/litigation/sessions/${sessionId}/`;
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('WebSocket 连接成功');
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket 错误:', error);
            };

            this.ws.onclose = () => {
                console.log('WebSocket 连接关闭');
            };
        },

        handleWebSocketMessage(data) {
            switch (data.type) {
                case 'history_message':
                    // 历史消息已在 loadMessages 中加载，忽略
                    break;
                case 'history_loaded':
                    console.log('历史消息加载完成');
                    break;
                case 'system_message':
                    this.messages.push({
                        role: 'system',
                        content: data.content,
                        created_at: new Date().toISOString(),
                        metadata: data.metadata || {}
                    });
                    this.$nextTick(() => this.scrollToBottom());
                    this.focusInput();
                    break;
                case 'assistant_chunk':
                    // 处理流式响应
                    const lastMsg = this.messages[this.messages.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.completed) {
                        lastMsg.content += data.content;
                    } else {
                        this.messages.push({
                            role: 'assistant',
                            content: data.content,
                            created_at: new Date().toISOString(),
                            metadata: {},
                            completed: false
                        });
                    }
                    this.$nextTick(() => this.scrollToBottom());
                    break;
                case 'assistant_complete':
                    const lastMessage = this.messages[this.messages.length - 1];
                    if (lastMessage && lastMessage.role === 'assistant') {
                        lastMessage.completed = true;
                        lastMessage.content = data.content;
                        lastMessage.metadata = data.metadata || lastMessage.metadata || {};
                    } else if (data.content) {
                        this.messages.push({
                            role: 'assistant',
                            content: data.content,
                            created_at: new Date().toISOString(),
                            metadata: data.metadata || {},
                            completed: true
                        });
                    }
                    this.$nextTick(() => this.scrollToBottom());
                    this.focusInput();
                    break;
                case 'error':
                    console.error('服务端错误:', data.message);
                    break;
            }
        },

        sendMessage() {
            if (!this.inputMessage.trim() || !this.ws || this.sending) {
                return;
            }

            this.sending = true;

            // 添加用户消息到列表
            this.messages.push({
                role: 'user',
                content: this.inputMessage,
                created_at: new Date().toISOString(),
                metadata: {}
            });

            // 发送到服务器
            this.ws.send(JSON.stringify({
                type: 'user_message',
                content: this.inputMessage
            }));

            // 清空输入框
            this.inputMessage = '';
            this.sending = false;
            this.focusInput();
            this.$nextTick(() => this.scrollToBottom());
        },

        // ========== 工具方法 ==========
        scrollToBottom() {
            const container = this.$refs.messagesContainer;
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        },

        formatRelativeTime(dateString) {
            const date = new Date(dateString);
            const now = new Date();
            const diff = now - date;

            const minutes = Math.floor(diff / 60000);
            const hours = Math.floor(diff / 3600000);
            const days = Math.floor(diff / 86400000);

            if (minutes < 1) return '刚刚';
            if (minutes < 60) return `${minutes}分钟前`;
            if (hours < 24) return `${hours}小时前`;
            if (days < 7) return `${days}天前`;

            return date.toLocaleDateString('zh-CN', {
                month: '2-digit',
                day: '2-digit'
            });
        },

        formatFullTime(dateString) {
            const d = new Date(dateString);
            if (Number.isNaN(d.getTime())) return '';
            const y = d.getFullYear();
            const m = d.getMonth() + 1;
            const day = d.getDate();
            const hh = String(d.getHours()).padStart(2, '0');
            const mm = String(d.getMinutes()).padStart(2, '0');
            return `${y}年${m}月${day}日${hh}:${mm}`;
        },

        getStatusIcon(status) {
            const icons = {
                'active': '🟢',
                'completed': '⚪',
                'cancelled': '🔴'
            };
            return icons[status] || '⚪';
        },

        getDocumentTypeDisplay(type) {
            const types = {
                'complaint': '起诉状',
                'defense': '答辩状',
                'counterclaim': '反诉状',
                'counterclaim_defense': '反诉答辩状',
                '': '未指定'
            };
            return types[type] || '未指定';
        },

        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        }
    };
}

window.aiLitigationTabApp = aiLitigationTabApp;
