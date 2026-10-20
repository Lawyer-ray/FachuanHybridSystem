/**
 * Image Rotation Tool — 工具函数
 *
 * 纯函数集合，不依赖 Alpine.js 状态。
 */
window.ImageRotationUtils = (function () {
    'use strict';

    // EXIF Orientation 映射表
    var ORIENTATION_MAP = {
        1: 0,    // 正常
        2: 0,    // 水平翻转 (简化为0)
        3: 180,  // 旋转180°
        4: 0,    // 垂直翻转 (简化为0)
        5: 270,  // 顺时针90° + 水平翻转 (简化为270)
        6: 270,  // 顺时针90°
        7: 90,   // 逆时针90° + 水平翻转 (简化为90)
        8: 90    // 逆时针90°
    };

    /**
     * 生成唯一 ID
     */
    function generateId() {
        return 'img-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * 把任意角度归一到 0 / 90 / 180 / 270（顺时针为正）。
     * ONNX 检测返回 -90 / -270，手动累加也可能越过 360；
     * 直接拿原值做 `=== 90 || === 270` 判定会漏掉负角度，导致 canvas 按未旋转宽高比开尺寸、内容被裁。
     * @param {number} rotation
     * @returns {number}
     */
    function normalizeRotation(rotation) {
        var r = Math.round(Number(rotation) || 0) % 360;
        return r < 0 ? r + 360 : r;
    }

    /**
     * 读取 EXIF Orientation 标签（纯 JavaScript 实现）
     * @param {ArrayBuffer} arrayBuffer
     * @returns {number} orientation 值 (1-8)，未找到返回 1
     */
    function readExifOrientation(arrayBuffer) {
        var view = new DataView(arrayBuffer);

        // 检查 JPEG 标记
        if (view.getUint16(0, false) !== 0xFFD8) {
            return 1;  // 不是 JPEG，返回默认值
        }

        var offset = 2;
        var length = view.byteLength;

        while (offset < length) {
            if (view.getUint8(offset) !== 0xFF) {
                return 1;
            }

            var marker = view.getUint8(offset + 1);

            // APP1 标记 (EXIF)
            if (marker === 0xE1) {
                var exifOffset = offset + 4;

                // 检查 "Exif\0\0" 标识
                if (view.getUint32(exifOffset, false) !== 0x45786966 ||
                    view.getUint16(exifOffset + 4, false) !== 0x0000) {
                    return 1;
                }

                var tiffOffset = exifOffset + 6;
                var littleEndian = view.getUint16(tiffOffset, false) === 0x4949;

                // 检查 TIFF 标记
                if (view.getUint16(tiffOffset + 2, littleEndian) !== 0x002A) {
                    return 1;
                }

                var firstIFDOffset = view.getUint32(tiffOffset + 4, littleEndian);
                var ifdOffset = tiffOffset + firstIFDOffset;
                var numEntries = view.getUint16(ifdOffset, littleEndian);

                // 遍历 IFD 条目查找 Orientation 标签 (0x0112)
                for (var i = 0; i < numEntries; i++) {
                    var entryOffset = ifdOffset + 2 + (i * 12);
                    var tag = view.getUint16(entryOffset, littleEndian);

                    if (tag === 0x0112) {  // Orientation 标签
                        return view.getUint16(entryOffset + 8, littleEndian);
                    }
                }
                return 1;
            }

            // 跳过其他标记
            if (marker === 0xD8 || marker === 0xD9) {
                offset += 2;
            } else {
                offset += 2 + view.getUint16(offset + 2, false);
            }
        }

        return 1;  // 未找到 Orientation，返回默认值
    }

    /**
     * 渲染缩略图到 Canvas
     * @param {string} canvasId — DOM canvas 元素的 id
     * @param {HTMLImageElement} img
     * @param {number} rotation — 当前总旋转角度
     */
    function renderThumbnail(canvasId, img, rotation) {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return;

        var ctx = canvas.getContext('2d');
        rotation = normalizeRotation(rotation);
        var isRotated90 = rotation === 90 || rotation === 270;
        var srcW = img.naturalWidth;
        var srcH = img.naturalHeight;
        var displayW = isRotated90 ? srcH : srcW;
        var displayH = isRotated90 ? srcW : srcH;

        // 计算缩放比例以适应 canvas
        var scale = Math.min(canvas.width / displayW, canvas.height / displayH);
        var drawW = displayW * scale;
        var drawH = displayH * scale;

        // 清空 canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // 居中绘制
        ctx.save();
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.rotate(rotation * Math.PI / 180);

        if (isRotated90) {
            ctx.drawImage(img, -drawH / 2, -drawW / 2, drawH, drawW);
        } else {
            ctx.drawImage(img, -drawW / 2, -drawH / 2, drawW, drawH);
        }

        ctx.restore();
    }

    /**
     * 渲染大图预览到指定 Canvas
     * @param {HTMLCanvasElement} canvas
     * @param {HTMLImageElement} img
     * @param {number} rotation
     */
    function renderModalPreview(canvas, img, rotation) {
        if (!canvas) return;

        var ctx = canvas.getContext('2d');
        rotation = normalizeRotation(rotation);
        var isRotated90 = rotation === 90 || rotation === 270;
        var srcW = img.naturalWidth;
        var srcH = img.naturalHeight;
        var displayW = isRotated90 ? srcH : srcW;
        var displayH = isRotated90 ? srcW : srcH;

        // 限制最大尺寸
        var maxW = window.innerWidth * 0.7;
        var maxH = window.innerHeight * 0.6;
        var scale = Math.min(1, maxW / displayW, maxH / displayH);

        // Canvas 尺寸为旋转后的显示尺寸
        canvas.width = displayW * scale;
        canvas.height = displayH * scale;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.save();
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.rotate(rotation * Math.PI / 180);

        var drawW = srcW * scale;
        var drawH = srcH * scale;

        ctx.drawImage(img, -drawW / 2, -drawH / 2, drawW, drawH);
        ctx.restore();
    }

    /**
     * File → Base64（不含 data: 前缀）
     * @param {File} file
     * @returns {Promise<string>}
     */
    function fileToBase64(file) {
        return new Promise(function (resolve, reject) {
            var reader = new FileReader();
            reader.onload = function () {
                var base64 = reader.result.split(',')[1];
                resolve(base64);
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    /**
     * 对图片应用旋转后导出 JPEG Base64
     * @param {HTMLImageElement} img
     * @param {number} rotation
     * @returns {Promise<string>} base64（不含 data: 前缀）
     */
    function getRotatedBase64(img, rotation) {
        return new Promise(function (resolve) {
            rotation = normalizeRotation(rotation);
            var isRotated90 = rotation === 90 || rotation === 270;
            var srcW = img.naturalWidth;
            var srcH = img.naturalHeight;

            var canvas = document.createElement('canvas');
            canvas.width = isRotated90 ? srcH : srcW;
            canvas.height = isRotated90 ? srcW : srcH;

            var ctx = canvas.getContext('2d');
            ctx.translate(canvas.width / 2, canvas.height / 2);
            ctx.rotate(rotation * Math.PI / 180);
            ctx.drawImage(img, -srcW / 2, -srcH / 2, srcW, srcH);

            var dataUrl = canvas.toDataURL('image/jpeg', 0.85);
            var base64 = dataUrl.split(',')[1];
            resolve(base64);
        });
    }

    // 公开 API
    return {
        ORIENTATION_MAP: ORIENTATION_MAP,
        generateId: generateId,
        normalizeRotation: normalizeRotation,
        readExifOrientation: readExifOrientation,
        renderThumbnail: renderThumbnail,
        renderModalPreview: renderModalPreview,
        fileToBase64: fileToBase64,
        getRotatedBase64: getRotatedBase64
    };
})();
