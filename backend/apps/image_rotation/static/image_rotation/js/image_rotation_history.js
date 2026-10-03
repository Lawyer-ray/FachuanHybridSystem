/**
 * Image Rotation Tool — 历史任务模块
 *
 * 任务保存、加载、删除、重命名、OCR 重识别、同步。
 */
window.ImageRotationHistory = (function () {
    'use strict';

    var U = window.ImageRotationUtils;

    function markChanged(imageId) {
        console.log('[DEBUG] markChanged called:', { imageId: imageId, onnxComplete: this.onnxComplete });
        if (!this.onnxComplete) return;
        this._changeBuffer[imageId] = true;
        clearTimeout(this._syncTimer);
        var self = this;
        this._syncTimer = setTimeout(function () { syncChangesToBackend.call(self); }, 800);
    }

    async function syncChangesToBackend() {
        var ids = Object.keys(this._changeBuffer);
        this._changeBuffer = {};
        if (ids.length === 0) return;

        if (!this.currentJobId) {
            if (this._savingHistory) {
                var self = this;
                ids.forEach(function (id) { self._changeBuffer[id] = true; });
                this._syncTimer = setTimeout(function () { syncChangesToBackend.call(self); }, 1000);
                return;
            }
            this._savingHistory = true;
            await saveTaskToHistory.call(this);
            this._savingHistory = false;
            if (Object.keys(this._changeBuffer).length > 0) {
                var self2 = this;
                this._syncTimer = setTimeout(function () { syncChangesToBackend.call(self2); }, 100);
            }
            return;
        }

        var pages = [];
        for (var i = 0; i < ids.length; i++) {
            var id = ids[i];
            var img = null;
            for (var j = 0; j < this.images.length; j++) {
                if (this.images[j].id === id) { img = this.images[j]; break; }
            }
            if (!img || !img._historyPageId) continue;
            var delta = ((img.rotation || 0) - (img.autoRotation || 0) + 360) % 360;
            console.log('[DEBUG] syncChangesToBackend:', {
                id: id,
                rotation: img.rotation,
                autoRotation: img.autoRotation,
                delta: delta,
                pageId: img._historyPageId
            });
            pages.push({
                page_id: img._historyPageId,
                detected_rotation: delta,
                suggested_filename: img.suggestedFilename || ''
            });
        }
        if (pages.length === 0) return;

        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        console.log('[DEBUG] Sending PATCH with pages:', pages);
        try {
            var resp = await fetch('/api/v1/image-rotation/jobs/' + this.currentJobId + '/pages', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ pages: pages })
            });
            var result = await resp.json();
            console.log('[DEBUG] PATCH response:', result);
        } catch (err) {
            console.warn('同步变化失败:', err);
        }
    }

    async function saveTaskToHistory() {
        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

        try {
            var formData = new FormData();
            formData.append('name', this.taskName || '');

            var pagesMeta = this.images.map(function (img, idx) {
                return {
                    filename: img.filename,
                    detected_rotation: 0,
                    onnx_rotation: img.autoRotation || 0,
                    detection_confidence: 0,
                    source_type: img.sourceType || 'image',
                    page_number: idx
                };
            });
            console.log('[DEBUG] saveTaskToHistory pagesMeta (before):', pagesMeta.map(function (p) {
                return { filename: p.filename, onnx_rotation: p.onnx_rotation, detected_rotation: p.detected_rotation };
            }));
            formData.append('pages', JSON.stringify(pagesMeta));

            for (var i = 0; i < this.images.length; i++) {
                var img = this.images[i];
                var blob;
                if (img.sourceType === 'pdf_page' && img.data) {
                    var resp = await fetch(img.data);
                    blob = await resp.blob();
                    pagesMeta[i].onnx_rotation = 0;
                } else if (img.file) {
                    blob = img.file;
                } else {
                    var canvas = document.createElement('canvas');
                    var source = img.img;
                    var srcW = source.naturalWidth || source.width;
                    var srcH = source.naturalHeight || source.height;
                    var renderRotation = img.autoRotation || 0;
                    var isRightAngle = (renderRotation % 180 !== 0);
                    canvas.width = isRightAngle ? srcH : srcW;
                    canvas.height = isRightAngle ? srcW : srcH;
                    var ctx = canvas.getContext('2d');
                    ctx.translate(canvas.width / 2, canvas.height / 2);
                    ctx.rotate(renderRotation * Math.PI / 180);
                    ctx.drawImage(source, -srcW / 2, -srcH / 2);
                    blob = await new Promise(function (resolve) { canvas.toBlob(resolve, 'image/jpeg', 0.85); });
                    pagesMeta[i].onnx_rotation = 0;
                }
                formData.append('source_' + i, blob, img.filename);
            }

            formData.set('pages', JSON.stringify(pagesMeta));
            console.log('[DEBUG] saveTaskToHistory pagesMeta (after):', pagesMeta.map(function (p) {
                return { filename: p.filename, onnx_rotation: p.onnx_rotation, detected_rotation: p.detected_rotation };
            }));

            var response = await fetch('/api/v1/image-rotation/jobs', {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken },
                body: formData
            });

            var result = await response.json();
            console.log('[DEBUG] saveTaskToHistory response:', result);
            if (result.success) {
                this.currentJobId = result.job_id;
                this.showSaveNotification = true;
                if (result.page_ids) {
                    for (var pi = 0; pi < this.images.length && pi < result.page_ids.length; pi++) {
                        this.images[pi]._historyPageId = result.page_ids[pi];
                    }
                }
                console.log('[DEBUG] currentJobId:', this.currentJobId, 'pageIds:', this.images.map(function (i) {
                    return { id: i.id, pageId: i._historyPageId };
                }));
            }
        } catch (err) {
            console.warn('保存历史任务失败:', err);
        }
    }

    async function saveExportUrl(fileType, mediaUrl) {
        if (!this.currentJobId && this.images.length > 0) {
            await saveTaskToHistory.call(this);
        }
        var jobId = this.currentJobId;
        if (!jobId) return;
        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        try {
            await fetch('/api/v1/image-rotation/jobs/' + jobId + '/save-export-url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ file_type: fileType, media_url: mediaUrl })
            });
        } catch (err) {
            console.warn('保存导出 URL 失败:', err);
        }
    }

    async function updateJobName() {
        if (!this.currentJobId) return;
        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        this.nameUpdatePending = true;
        try {
            var resp = await fetch('/api/v1/image-rotation/jobs/' + this.currentJobId, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ name: this.taskName || '' })
            });
            var data = await resp.json();
            if (data.success) {
                this.nameUpdatePending = false;
            }
        } catch (err) {
            console.warn('更新名称失败:', err);
            this.nameUpdatePending = false;
        }
    }

    async function renameJobFromHistory(jobId) {
        var newName = prompt('请输入新的任务名称：');
        if (newName === null) return;
        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        try {
            var resp = await fetch('/api/v1/image-rotation/jobs/' + jobId, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ name: newName.trim() })
            });
            var data = await resp.json();
            if (data.success) {
                var job = null;
                for (var i = 0; i < this.historyJobs.length; i++) {
                    if (this.historyJobs[i].id === jobId) { job = this.historyJobs[i]; break; }
                }
                if (job) { job.display_name = data.display_name; }
                if (this.historyDetail && this.historyDetail.id === jobId) {
                    this.historyDetail.display_name = data.display_name;
                }
            }
        } catch (err) {
            console.warn('重命名失败:', err);
        }
    }

    async function exportFromHistory(fileType) {
        if (!this.historyDetailPages || this.historyDetailPages.length === 0) return;
        this.historyExporting = true;
        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

        try {
            if (fileType === 'zip') {
                var formData = new FormData();
                formData.append('paper_size', this.historyPaperSize);
                for (var i = 0; i < this.historyDetailPages.length; i++) {
                    var page = this.historyDetailPages[i];
                    var resp = await fetch(page.source_image_url);
                    var blob = await resp.blob();
                    formData.append('image_' + i, blob, page.original_filename);
                    formData.append('filename_' + i, page.suggested_filename || page.original_filename);
                    formData.append('format_' + i, 'jpeg');
                    formData.append('rotation_' + i, String(((page.onnx_rotation || 0) + (page.detected_rotation || 0)) % 360));
                }
                var resp2 = await fetch('/api/v1/image-rotation/export', {
                    method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body: formData
                });
                var result = await resp2.json();
                if (result.success && result.zip_url) {
                    window.open(result.zip_url, '_blank');
                    if (this.historyDetail) { saveExportUrl.call(this, 'zip', result.zip_url); }
                }
            } else {
                var formData2 = new FormData();
                formData2.append('paper_size', this.historyPaperSize);
                for (var j = 0; j < this.historyDetailPages.length; j++) {
                    var page2 = this.historyDetailPages[j];
                    var resp3 = await fetch(page2.source_image_url);
                    var blob2 = await resp3.blob();
                    formData2.append('page_' + j, blob2, page2.original_filename);
                    formData2.append('filename_' + j, page2.original_filename);
                    formData2.append('rotation_' + j, String(((page2.onnx_rotation || 0) + (page2.detected_rotation || 0)) % 360));
                }
                var resp4 = await fetch('/api/v1/image-rotation/export-pdf', {
                    method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body: formData2
                });
                var result2 = await resp4.json();
                if (result2.success && result2.pdf_url) {
                    window.open(result2.pdf_url, '_blank');
                    if (this.historyDetail) { saveExportUrl.call(this, 'pdf', result2.pdf_url); }
                }
            }
        } catch (err) {
            console.warn('导出失败:', err);
        } finally {
            this.historyExporting = false;
        }
    }

    async function loadJobToTool() {
        if (!this.historyDetail || !this.historyDetailPages.length) return;
        this.loading = true;
        this.loadingText = '加载任务...';

        this.images.forEach(function (img) { if (img.img) URL.revokeObjectURL(img.img.src); });
        this.images = [];
        this.selectedImage = null;
        this.errors = [];
        this.showOcrPrompt = false;
        this.ocrProcessing = false;
        this.totalDetectionTimeMs = 0;

        this.taskName = this.historyDetail.name || '';
        this.currentJobId = null;
        this.onnxComplete = true;
        this.pdfPending = 0;
        this._savingHistory = false;
        this.showSaveNotification = false;

        try {
            for (var i = 0; i < this.historyDetailPages.length; i++) {
                var page = this.historyDetailPages[i];
                var img = new Image();
                await new Promise(function (resolve, reject) {
                    img.onload = resolve;
                    img.onerror = reject;
                    img.src = page.source_image_url;
                });

                var imageItem = {
                    id: U.generateId(),
                    filename: page.suggested_filename || page.original_filename,
                    img: img,
                    data: null,
                    rotation: page.detected_rotation || 0,
                    autoRotation: page.onnx_rotation || 0,
                    sourceType: page.source_type || 'image',
                    format: 'jpeg',
                    size: 0,
                    status: 'processed',
                    needsDetection: false,
                    detectionTimeMs: 0,
                    suggestedFilename: page.suggested_filename || '',
                    ocrText: page.ocr_text || '',
                    _historyPageId: page.id
                };
                this.images.push(imageItem);
                await this.$nextTick();
                this.renderThumbnail(imageItem);
            }

            this.currentView = 'tool';
            this.showOcrPrompt = false;
        } catch (err) {
            console.warn('加载任务失败:', err);
        } finally {
            this.loading = false;
        }
    }

    function openHistoryPreview(page) {
        this.historyPreviewPage = page;
    }

    async function loadHistory(page) {
        page = page || 1;
        this.historyLoading = true;
        try {
            var resp = await fetch('/api/v1/image-rotation/jobs?page=' + page + '&page_size=20');
            var data = await resp.json();
            if (Array.isArray(data.items)) {
                this.historyJobs = data.items;
                this.historyPage = data.page;
                this.historyTotalCount = data.total;
            }
        } catch (err) {
            console.warn('加载历史记录失败:', err);
        } finally {
            this.historyLoading = false;
        }
    }

    async function viewJobDetail(jobId) {
        try {
            var resp = await fetch('/api/v1/image-rotation/jobs/' + jobId);
            var data = await resp.json();
            console.log('[DEBUG] viewJobDetail response:', data);
            if (data.success) {
                this.historyDetail = data.job;
                this.historyDetailPages = data.pages;
                console.log('[DEBUG] historyDetailPages:', data.pages.map(function (p) {
                    return {
                        id: p.id,
                        onnx_rotation: p.onnx_rotation,
                        detected_rotation: p.detected_rotation,
                        total: (p.onnx_rotation || 0) + (p.detected_rotation || 0)
                    };
                }));
            }
        } catch (err) {
            console.warn('加载任务详情失败:', err);
        }
    }

    async function reOcrJob(jobId, provider) {
        this.reOcrProcessing = true;
        this.reOcrJobId = jobId;
        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        try {
            var resp = await fetch('/api/v1/image-rotation/jobs/' + jobId + '/ocr', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ provider: provider })
            });
            var data = await resp.json();
            if (data.success) {
                if (this.historyDetail && this.historyDetail.id === jobId) {
                    this.historyDetailPages = data.pages;
                }
            }
        } catch (err) {
            console.warn('OCR 重识别失败:', err);
        } finally {
            this.reOcrProcessing = false;
            this.reOcrJobId = null;
        }
    }

    function downloadJobFile(jobId, fileType) {
        window.open('/api/v1/image-rotation/jobs/' + jobId + '/download/' + fileType, '_blank');
    }

    function confirmDeleteJob(jobId) {
        this.deleteTargetJobId = jobId;
        this.showDeleteConfirm = true;
    }

    async function executeDeleteJob() {
        var jobId = this.deleteTargetJobId;
        this.showDeleteConfirm = false;
        this.deleteTargetJobId = null;
        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        try {
            await fetch('/api/v1/image-rotation/jobs/' + jobId, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': csrfToken }
            });
            this.historyJobs = this.historyJobs.filter(function (j) { return j.id !== jobId; });
            if (this.historyDetail && this.historyDetail.id === jobId) {
                this.historyDetail = null;
                this.historyDetailPages = [];
            }
        } catch (err) {
            console.warn('删除任务失败:', err);
        }
    }

    return {
        markChanged: markChanged,
        syncChangesToBackend: syncChangesToBackend,
        saveTaskToHistory: saveTaskToHistory,
        saveExportUrl: saveExportUrl,
        updateJobName: updateJobName,
        renameJobFromHistory: renameJobFromHistory,
        exportFromHistory: exportFromHistory,
        loadJobToTool: loadJobToTool,
        openHistoryPreview: openHistoryPreview,
        loadHistory: loadHistory,
        viewJobDetail: viewJobDetail,
        reOcrJob: reOcrJob,
        downloadJobFile: downloadJobFile,
        confirmDeleteJob: confirmDeleteJob,
        executeDeleteJob: executeDeleteJob
    };
})();
