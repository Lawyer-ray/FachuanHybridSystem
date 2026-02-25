/**
 * 文件夹浏览器组件 - Finder 风格
 * 用于在合同编辑页绑定文件夹
 */

document.addEventListener('alpine:init', () => {
    Alpine.data('folderBrowser', (contractId) => ({
        contractId: contractId,
        showBrowser: false,
        loading: false,
        columns: [], // 分栏数据 [{path, entries, selectedIndex}]
        binding: null,
        error: null,
        manualPath: '', // 手动输入的路径

        init() {
            this.loadBinding();
        },

        async loadBinding() {
            if (!this.contractId) return;
            
            try {
                const response = await fetch(`/api/v1/contracts/${this.contractId}/folder-binding`, {
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    credentials: 'same-origin'
                });
                
                if (response.ok) {
                    const data = await response.json();
                    if (data) {
                        this.binding = data;
                    }
                } else if (response.status === 404) {
                    // 未绑定，正常情况
                    this.binding = null;
                } else {
                    console.error('加载绑定失败:', response.status);
                }
            } catch (error) {
                console.error('加载绑定失败:', error);
            }
        },

        async openBrowser() {
            this.showBrowser = true;
            this.error = null;
            this.columns = [];
            this.manualPath = this.binding?.folder_path || '';
            await this.loadRoots();
        },

        closeBrowser() {
            this.showBrowser = false;
            this.columns = [];
            this.error = null;
            this.manualPath = '';
        },

        async loadRoots() {
            this.loading = true;
            this.error = null;

            try {
                const response = await fetch('/api/v1/contracts/folder-browse', {
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    credentials: 'same-origin'
                });

                if (!response.ok) {
                    throw new Error('加载根目录失败');
                }

                const data = await response.json();
                
                if (!data.browsable) {
                    this.error = data.message || '无法访问根目录';
                    return;
                }

                this.columns = [{
                    path: null,
                    entries: data.entries || [],
                    selectedIndex: -1
                }];
            } catch (error) {
                console.error('加载根目录失败:', error);
                this.error = '加载根目录失败';
            } finally {
                this.loading = false;
            }
        },

        async selectFolder(columnIndex, entryIndex, entry) {
            // 防止重复点击
            if (this.loading) return;
            
            // 更新当前列的选中状态
            this.columns[columnIndex].selectedIndex = entryIndex;
            
            // 移除后续的列
            this.columns = this.columns.slice(0, columnIndex + 1);
            
            // 加载子文件夹
            await this.loadSubfolders(entry.path);
        },

        async loadSubfolders(path) {
            this.loading = true;
            this.error = null;

            try {
                const response = await fetch(`/api/v1/contracts/folder-browse?path=${encodeURIComponent(path)}`, {
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    credentials: 'same-origin'
                });

                if (!response.ok) {
                    throw new Error('加载文件夹失败');
                }

                const data = await response.json();
                
                if (!data.browsable) {
                    this.error = data.message || '无法访问此路径';
                    return;
                }

                // 添加新列
                if (data.entries && data.entries.length > 0) {
                    this.columns.push({
                        path: path,
                        entries: data.entries,
                        selectedIndex: -1
                    });
                }
                
                // 更新手动输入框
                this.manualPath = path;
            } catch (error) {
                console.error('加载文件夹失败:', error);
                this.error = '加载文件夹失败';
            } finally {
                this.loading = false;
            }
        },

        async bindManualPath() {
            if (!this.manualPath || !this.manualPath.trim()) {
                this.error = '请输入文件夹路径';
                return;
            }

            await this.selectFolderPath(this.manualPath.trim());
        },

        async selectFolderPath(path) {
            this.loading = true;
            this.error = null;

            try {
                const response = await fetch(`/api/v1/contracts/${this.contractId}/folder-binding`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    credentials: 'same-origin',
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

        getCurrentPath() {
            // 获取最后一个选中的路径
            for (let i = this.columns.length - 1; i >= 0; i--) {
                const col = this.columns[i];
                if (col.selectedIndex >= 0 && col.entries[col.selectedIndex]) {
                    return col.entries[col.selectedIndex].path;
                }
            }
            return null;
        },

        async bindCurrentPath() {
            const path = this.getCurrentPath();
            if (!path) {
                this.error = '请选择一个文件夹';
                return;
            }
            await this.selectFolderPath(path);
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
                    },
                    credentials: 'same-origin'
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
