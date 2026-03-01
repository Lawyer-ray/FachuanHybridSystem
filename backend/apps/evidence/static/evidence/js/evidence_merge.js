/**
 * 证据清单合并 PDF 功能
 *
 * 提供异步合并、进度显示、状态轮询功能
 */

(function() {
    'use strict';

    // 合并状态常量
    const MergeStatus = {
        PENDING: 'pending',
        PROCESSING: 'processing',
        COMPLETED: 'completed',
        FAILED: 'failed'
    };

    // 轮询间隔（毫秒）
    const POLL_INTERVAL = 1000;

    // 当前轮询定时器
    let pollTimer = null;

    /**
     * 初始化合并功能
     */
    function init() {
        // 绑定合并按钮点击事件
        document.addEventListener('click', function(e) {
            const mergeBtn = e.target.closest('a[href*="/merge/"]');
            if (mergeBtn && !mergeBtn.classList.contains('merge-processing')) {
                e.preventDefault();
                startMerge(mergeBtn);
            }
        });

        // 页面加载时检查是否有正在进行的合并任务
        checkInitialStatus();
    }

    /**
     * 检查初始状态
     */
    function checkInitialStatus() {
        const pk = getEvidenceListPk();
        if (!pk) return;

        fetch(`/admin/documents/evidencelist/${pk}/merge-status/`)
            .then(response => response.json())
            .then(data => {
                if (data.status === MergeStatus.PROCESSING) {
                    showMergeProgress(data);
                    startPolling(pk);
                }
            })
            .catch(err => console.error('检查合并状态失败:', err));
    }

    /**
     * 获取证据清单 ID
     */
    function getEvidenceListPk() {
        // 从 URL 中提取 ID
        const match = window.location.pathname.match(/\/evidencelist\/(\d+)\//);
        return match ? match[1] : null;
    }

    /**
     * 开始合并
     */
    function startMerge(btn) {
        const href = btn.getAttribute('href');
        const pk = href.match(/\/(\d+)\/merge\//)?.[1];
        if (!pk) return;

        // 禁用按钮
        btn.classList.add('merge-processing');
        btn.style.pointerEvents = 'none';
        btn.style.opacity = '0.6';

        // 显示加载状态
        showMergeProgress({ status: MergeStatus.PROCESSING, message: '正在提交合并任务...' });

        // 发送合并请求
        fetch(href, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showMergeProgress({ status: MergeStatus.PROCESSING, message: '合并任务已提交，正在处理...' });
                startPolling(pk);
            } else {
                showMergeError(data.error || '提交合并任务失败');
                resetMergeButton(btn);
            }
        })
        .catch(err => {
            console.error('提交合并任务失败:', err);
            showMergeError('提交合并任务失败，请重试');
            resetMergeButton(btn);
        });
    }

    /**
     * 开始轮询状态
     */
    function startPolling(pk) {
        if (pollTimer) {
            clearInterval(pollTimer);
        }

        pollTimer = setInterval(() => {
            fetch(`/admin/documents/evidencelist/${pk}/merge-status/`)
                .then(response => response.json())
                .then(data => {
                    showMergeProgress(data);

                    if (data.status === MergeStatus.COMPLETED) {
                        stopPolling();
                        showMergeSuccess(data);
                    } else if (data.status === MergeStatus.FAILED) {
                        stopPolling();
                        showMergeError(data.error || '合并失败');
                    }
                })
                .catch(err => {
                    console.error('获取合并状态失败:', err);
                });
        }, POLL_INTERVAL);
    }

    /**
     * 停止轮询
     */
    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    /**
     * 显示合并进度
     */
    function showMergeProgress(data) {
        let overlay = document.getElementById('merge-overlay');
        if (!overlay) {
            overlay = createOverlay();
        }

        const content = overlay.querySelector('.merge-content');
        const progress = data.progress || 0;
        const message = data.message || '正在处理...';

        content.innerHTML = `
            <div class="merge-spinner"></div>
            <div class="merge-title">正在合并 PDF</div>
            <div class="merge-progress-bar">
                <div class="merge-progress-fill" style="width: ${progress}%"></div>
            </div>
            <div class="merge-message">${message}</div>
            <div class="merge-detail">${data.current || 0} / ${data.total || 0} 个文件</div>
        `;

        overlay.style.display = 'flex';
    }

    /**
     * 显示合并成功
     */
    function showMergeSuccess(data) {
        let overlay = document.getElementById('merge-overlay');
        if (!overlay) {
            overlay = createOverlay();
        }

        const content = overlay.querySelector('.merge-content');
        content.innerHTML = `
            <div class="merge-success-icon">✓</div>
            <div class="merge-title" style="color: #2e7d32;">合并 PDF 成功</div>
            <div class="merge-message">共 ${data.total_pages || 0} 页</div>
            <div class="merge-detail">${data.pdf_filename || ''}</div>
            <button class="merge-close-btn" onclick="window.location.reload()">确定</button>
        `;

        // 3秒后自动刷新页面
        setTimeout(() => {
            window.location.reload();
        }, 2000);
    }

    /**
     * 显示合并错误
     */
    function showMergeError(error) {
        let overlay = document.getElementById('merge-overlay');
        if (!overlay) {
            overlay = createOverlay();
        }

        const content = overlay.querySelector('.merge-content');
        content.innerHTML = `
            <div class="merge-error-icon">✕</div>
            <div class="merge-title" style="color: #d32f2f;">合并失败</div>
            <div class="merge-message">${error}</div>
            <button class="merge-close-btn" onclick="document.getElementById('merge-overlay').style.display='none'">关闭</button>
        `;
    }

    /**
     * 创建遮罩层
     */
    function createOverlay() {
        const overlay = document.createElement('div');
        overlay.id = 'merge-overlay';
        overlay.innerHTML = `
            <style>
                #merge-overlay {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0, 0, 0, 0.5);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 10000;
                }
                .merge-content {
                    background: white;
                    padding: 32px 48px;
                    border-radius: 8px;
                    text-align: center;
                    min-width: 320px;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
                }
                .merge-spinner {
                    width: 48px;
                    height: 48px;
                    border: 4px solid #e0e0e0;
                    border-top-color: #1976d2;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 16px;
                }
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
                .merge-title {
                    font-size: 18px;
                    font-weight: 600;
                    margin-bottom: 16px;
                    color: #333;
                }
                .merge-progress-bar {
                    width: 100%;
                    height: 8px;
                    background: #e0e0e0;
                    border-radius: 4px;
                    overflow: hidden;
                    margin-bottom: 12px;
                }
                .merge-progress-fill {
                    height: 100%;
                    background: #1976d2;
                    transition: width 0.3s ease;
                }
                .merge-message {
                    color: #666;
                    font-size: 14px;
                    margin-bottom: 8px;
                }
                .merge-detail {
                    color: #999;
                    font-size: 12px;
                }
                .merge-success-icon {
                    width: 48px;
                    height: 48px;
                    background: #2e7d32;
                    color: white;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 24px;
                    margin: 0 auto 16px;
                }
                .merge-error-icon {
                    width: 48px;
                    height: 48px;
                    background: #d32f2f;
                    color: white;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 24px;
                    margin: 0 auto 16px;
                }
                .merge-close-btn {
                    margin-top: 16px;
                    padding: 8px 24px;
                    background: #1976d2;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                }
                .merge-close-btn:hover {
                    background: #1565c0;
                }
            </style>
            <div class="merge-content"></div>
        `;
        document.body.appendChild(overlay);
        return overlay;
    }

    /**
     * 重置合并按钮
     */
    function resetMergeButton(btn) {
        btn.classList.remove('merge-processing');
        btn.style.pointerEvents = '';
        btn.style.opacity = '';
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
