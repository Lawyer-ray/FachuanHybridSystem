/**
 * Image Rotation Tool — 导出模块
 *
 * PDF / ZIP 导出。
 */
window.ImageRotationExport = (function () {
    'use strict';

    var U = window.ImageRotationUtils;

    // 获取图片的 Base64 数据（应用旋转，使用 JPEG 压缩）
    function getRotatedImageData(imageItem) {
        return new Promise(function (resolve) {
            var img = imageItem.img;
            var rotation = U.normalizeRotation(imageItem.rotation);

            var isRotated90 = rotation === 90 || rotation === 270;
            var srcW = img.naturalWidth;
            var srcH = img.naturalHeight;

            var canvas = document.createElement('canvas');
            canvas.width = isRotated90 ? srcH : srcW;
            canvas.height = isRotated90 ? srcW : srcH;

            var ctx = canvas.getContext('2d');
            ctx.translate(canvas.width / 2, canvas.height / 2);
            ctx.rotate(rotation * Math.PI / 180);

            if (isRotated90) {
                ctx.drawImage(img, -srcW / 2, -srcH / 2, srcW, srcH);
            } else {
                ctx.drawImage(img, -srcW / 2, -srcH / 2, srcW, srcH);
            }

            var dataUrl = canvas.toDataURL('image/jpeg', 0.85);
            var base64 = dataUrl.split(',')[1];
            resolve(base64);
        });
    }

    // 导出 PDF
    async function exportPdf() {
        if (this.images.length === 0) return;

        this.processing = true;
        this.loading = true;
        this.loadingText = '正在生成 PDF...';
        this.progress = 0;
        this.errors = [];

        try {
            var pagesData = [];
            for (var i = 0; i < this.images.length; i++) {
                var img = this.images[i];
                this.progress = Math.round((i / this.images.length) * 50);
                this.loadingText = '处理页面 (' + (i + 1) + '/' + this.images.length + ')...';

                var base64Data = await getRotatedImageData(img);
                pagesData.push({
                    filename: img.filename,
                    data: base64Data,
                    rotation: 0,
                    source_type: img.sourceType || 'image'
                });
            }

            this.progress = 60;
            this.loadingText = '正在生成 PDF 文件...';

            var formData = new FormData();
            formData.append('paper_size', this.paperSize);

            for (var j = 0; j < pagesData.length; j++) {
                var pageData = pagesData[j];
                var byteCharacters = atob(pageData.data);
                var byteNumbers = new Array(byteCharacters.length);
                for (var k = 0; k < byteCharacters.length; k++) {
                    byteNumbers[k] = byteCharacters.charCodeAt(k);
                }
                var byteArray = new Uint8Array(byteNumbers);
                var blob = new Blob([byteArray], { type: 'image/jpeg' });

                formData.append('page_' + j, blob, pageData.filename);
                formData.append('filename_' + j, pageData.filename);
            }

            var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            var response = await fetch('/api/v1/image-rotation/export-pdf', {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken },
                body: formData
            });

            this.progress = 90;
            var result = await response.json();

            if (result.success && result.pdf_url) {
                this.progress = 100;
                this.loadingText = '下载中...';

                var link = document.createElement('a');
                link.href = result.pdf_url;
                link.download = '';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

                if (this.currentJobId) {
                    this.saveExportUrl('pdf', result.pdf_url);
                }
                this.errors = [];
            } else {
                this.errors.push('导出失败: ' + (result.message || '未知错误'));
            }
        } catch (err) {
            this.errors.push('导出失败: ' + err.message);
        } finally {
            this.processing = false;
            this.loading = false;
            this.progress = 0;
        }
    }

    // 导出 ZIP（仅图片）
    async function exportZip() {
        if (this.images.length === 0) return;

        this.processing = true;
        this.loading = true;
        this.loadingText = '正在生成 ZIP...';
        this.progress = 0;
        this.errors = [];

        try {
            var imagesData = [];
            var renameMap = {};

            for (var i = 0; i < this.images.length; i++) {
                var img = this.images[i];
                this.progress = Math.round((i / this.images.length) * 50);
                this.loadingText = '处理图片 (' + (i + 1) + '/' + this.images.length + ')...';

                var base64Data = await getRotatedImageData(img);

                var filename = img.filename;
                if (!filename.match(/\.(jpg|jpeg|png)$/i)) {
                    filename = filename + '.jpg';
                }

                imagesData.push({
                    filename: filename,
                    data: base64Data,
                    rotation: 0,
                    format: 'jpeg'
                });

                if (img.suggestedFilename) {
                    var suggested = img.suggestedFilename;
                    if (!suggested.match(/\.(jpg|jpeg|png)$/i)) {
                        suggested = suggested + '.jpg';
                    }
                    renameMap[filename] = suggested;
                }
            }

            this.progress = 60;
            this.loadingText = '正在生成 ZIP 文件...';

            var formData = new FormData();
            formData.append('paper_size', this.paperSize);
            if (Object.keys(renameMap).length > 0) {
                formData.append('rename_map', JSON.stringify(renameMap));
            }

            for (var j = 0; j < imagesData.length; j++) {
                var imgData = imagesData[j];
                var byteCharacters = atob(imgData.data);
                var byteNumbers = new Array(byteCharacters.length);
                for (var k = 0; k < byteCharacters.length; k++) {
                    byteNumbers[k] = byteCharacters.charCodeAt(k);
                }
                var byteArray = new Uint8Array(byteNumbers);
                var blob = new Blob([byteArray], { type: 'image/jpeg' });

                formData.append('image_' + j, blob, imgData.filename);
                formData.append('filename_' + j, imgData.filename);
                formData.append('format_' + j, imgData.format);
            }

            var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            var response = await fetch('/api/v1/image-rotation/export', {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken },
                body: formData
            });

            this.progress = 90;
            var result = await response.json();

            if (result.success && result.zip_url) {
                this.progress = 100;
                this.loadingText = '下载中...';

                var link = document.createElement('a');
                link.href = result.zip_url;
                link.download = '';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

                if (this.currentJobId) {
                    this.saveExportUrl('zip', result.zip_url);
                }
                this.errors = [];
            } else {
                this.errors.push('导出失败: ' + (result.message || '未知错误'));
            }
        } catch (err) {
            this.errors.push('导出失败: ' + err.message);
        } finally {
            this.processing = false;
            this.loading = false;
            this.progress = 0;
        }
    }

    return {
        getRotatedImageData: getRotatedImageData,
        exportPdf: exportPdf,
        exportZip: exportZip
    };
})();
