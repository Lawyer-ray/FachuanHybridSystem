/**
 * 文件夹浏览器组件
 * 用于在合同编辑页绑定文件夹
 */

document.addEventListener('alpine:init', () => {
    Alpine.data('folderBrowser', (contractId) => ({
        contractId: contractId,
        showBrowser: false,
        loading: false,
        currentPath: null,
        parentPath: null,
        entries: [],
        binding: null,
        error: null,

        init() {
            this.loadBinding();
        },

        async loadBinding() {
            if (!this.contractId) return;
            
            try {
                const response = await fetch(`/api/v1/contracts/${this.contractId}/folder-binding`, {
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    }
                });
                
                if (response.ok) {
                    this.binding = await response.json();
                }
            } catch (error) {
                console.error('加载绑定失败:', error);
            }
        },

        async openBrowser() {
            this.showBrowser = true;
            this.error = null;
            await this.browseFolder(null);
        },

        closeBrowser() {
            this.showBrowser = false;
            this.currentPath = null;
            this.parentPath = null;
            this.entries = [];
            this.error = null;
        },

        async browseFolder(path) {
            this.loading = true;
            this.error = null;

            try {
                const url = path 
                    ? `/api/v1/contracts/folder-browse?path=${encodeURIComponent(path)}`
                    : '/api/v1/contracts/folder-browse';
                
                const response = await fetch(url, {
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    }
                });

                if (!response.ok) {
                    throw new Error('浏览文件夹失败');
                }

                const data = await response.json();
                
                if (!data.browsable) {
                    this.error = data.message || '无法访问此路径';
                    return;
                }

                this.currentPath = data.path;
                this.parentPath = data.parent_path;
                this.entries = data.entries || [];
            } catch (error) {
                console.error('浏览文件夹失败:', error);
                this.error = '加载文件夹失败';
            } finally {
                this.loading = false;
            }
        },

        async selectFolder(path) {
            this.loading = true;
            this.error = null;

            try {
                const response = await fetch(`/api/v1/contracts/${this.contractId}/folder-binding`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({ folder_path: path })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.message || '绑定失败');
                }

                this.binding = await response.json();
                this.closeBrowser();
                
                // 显示成功消息
                this.showMessage('文件夹绑定成功', 'success');
            } catch (error) {
                console.error('绑定文件夹失败:', error);
                this.error = error.message || '绑定失败';
            } finally {
                this.loading = false;
            }
        },

        async unbindFolder() {
            if (!confirm('确定要解除文件夹绑定吗？')) {
                return;
            }

            this.loading = true;

            try {
                const response = await fetch(`/api/v1/contracts/${this.contractId}/folder-binding`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    }
                });

                if (!response.ok) {
                    throw new Error('解除绑定失败');
                }

                this.binding = null;
                this.showMessage('已解除文件夹绑定', 'success');
            } catch (error) {
                console.error('解除绑定失败:', error);
                this.showMessage('解除绑定失败', 'error');
            } finally {
                this.loading = false;
            }
        },

        getCsrfToken() {
            return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        },

        showMessage(message, type) {
            // 使用 Django messages 框架显示消息
            const messagesDiv = document.querySelector('.messagelist');
            if (messagesDiv) {
                const messageItem = document.createElement('li');
                messageItem.className = type === 'success' ? 'success' : 'error';
                messageItem.textContent = message;
                messagesDiv.appendChild(messageItem);
                
                setTimeout(() => {
                    messageItem.remove();
                }, 3000);
            }
        }
    }));
});
