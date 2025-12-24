// ==UserScript==
// @name         法院网站验证码自动识别
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  自动识别法院网站登录页面的验证码
// @author       Your Name
// @match        https://zxfw.court.gov.cn/zxfw/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    // 配置
    const CONFIG = {
        API_URL: 'http://127.0.0.1:8000/api/v1/automation/captcha/recognize',
        CHECK_INTERVAL: 500, // 检查间隔（毫秒）
        MAX_RETRIES: 3, // 最大重试次数
        DEBUG: true // 调试模式
    };

    // XPath 选择器
    const SELECTORS = {
        PASSWORD_TAB: '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[2]/uni-view[2]',
        CAPTCHA_IMAGE: '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[2]/uni-image/img',
        CAPTCHA_INPUT: '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[1]/uni-view/uni-input/div/input',
        ERROR_MESSAGE: '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[4]'
    };

    // 状态管理
    let state = {
        isProcessing: false,
        retryCount: 0,
        lastCaptchaUrl: null,
        observer: null
    };

    // 日志函数
    function log(message, type = 'info') {
        if (!CONFIG.DEBUG && type === 'debug') return;
        const prefix = '[法院验证码识别]';
        const styles = {
            info: 'color: #2196F3',
            success: 'color: #4CAF50',
            error: 'color: #F44336',
            debug: 'color: #9E9E9E'
        };
        console.log(`%c${prefix} ${message}`, styles[type] || styles.info);
    }

    // 通过 XPath 获取元素
    function getElementByXPath(xpath) {
        return document.evaluate(
            xpath,
            document,
            null,
            XPathResult.FIRST_ORDERED_NODE_TYPE,
            null
        ).singleNodeValue;
    }

    // 等待元素出现
    function waitForElement(xpath, timeout = 10000) {
        return new Promise((resolve, reject) => {
            const startTime = Date.now();
            const checkInterval = setInterval(() => {
                const element = getElementByXPath(xpath);
                if (element) {
                    clearInterval(checkInterval);
                    resolve(element);
                } else if (Date.now() - startTime > timeout) {
                    clearInterval(checkInterval);
                    reject(new Error(`元素未找到: ${xpath}`));
                }
            }, CONFIG.CHECK_INTERVAL);
        });
    }

    // 将图片转换为 Base64
    function imageToBase64(img) {
        return new Promise((resolve, reject) => {
            try {
                const canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth || img.width;
                canvas.height = img.naturalHeight || img.height;
                
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                
                const base64 = canvas.toDataURL('image/png').split(',')[1];
                resolve(base64);
            } catch (error) {
                reject(error);
            }
        });
    }

    // 调用后端 API 识别验证码
    function recognizeCaptcha(base64Image) {
        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method: 'POST',
                url: CONFIG.API_URL,
                headers: {
                    'Content-Type': 'application/json'
                },
                data: JSON.stringify({
                    image_base64: base64Image
                }),
                timeout: 10000,
                onload: function(response) {
                    try {
                        const result = JSON.parse(response.responseText);
                        if (result.success && result.text) {
                            resolve(result.text);
                        } else {
                            reject(new Error(result.error || '识别失败'));
                        }
                    } catch (error) {
                        reject(new Error('解析响应失败: ' + error.message));
                    }
                },
                onerror: function(error) {
                    reject(new Error('API 请求失败: ' + error));
                },
                ontimeout: function() {
                    reject(new Error('API 请求超时'));
                }
            });
        });
    }

    // 填充验证码
    function fillCaptcha(text) {
        const input = getElementByXPath(SELECTORS.CAPTCHA_INPUT);
        if (!input) {
            throw new Error('验证码输入框未找到');
        }

        // 设置值
        input.value = text;
        
        // 触发输入事件
        const events = ['input', 'change', 'blur'];
        events.forEach(eventType => {
            const event = new Event(eventType, { bubbles: true });
            input.dispatchEvent(event);
        });

        log(`验证码已填充: ${text}`, 'success');
    }

    // 处理验证码识别
    async function processCaptcha() {
        if (state.isProcessing) {
            log('正在处理中，跳过...', 'debug');
            return;
        }

        state.isProcessing = true;

        try {
            log('开始识别验证码...', 'info');

            // 获取验证码图片
            const captchaImg = getElementByXPath(SELECTORS.CAPTCHA_IMAGE);
            if (!captchaImg) {
                throw new Error('验证码图片未找到');
            }

            // 检查图片是否已加载
            if (!captchaImg.complete || captchaImg.naturalWidth === 0) {
                log('等待验证码图片加载...', 'debug');
                await new Promise(resolve => {
                    captchaImg.onload = resolve;
                    setTimeout(resolve, 3000); // 超时保护
                });
            }

            // 检查是否是同一张图片
            const currentUrl = captchaImg.src;
            if (currentUrl === state.lastCaptchaUrl) {
                log('验证码图片未更新，跳过识别', 'debug');
                state.isProcessing = false;
                return;
            }
            state.lastCaptchaUrl = currentUrl;

            // 转换为 Base64
            log('转换图片为 Base64...', 'debug');
            const base64Image = await imageToBase64(captchaImg);

            // 调用 API 识别
            log('调用识别 API...', 'debug');
            const captchaText = await recognizeCaptcha(base64Image);

            // 填充验证码
            fillCaptcha(captchaText);

            state.retryCount = 0;
            log(`✅ 验证码识别成功: ${captchaText}`, 'success');

        } catch (error) {
            log(`❌ 识别失败: ${error.message}`, 'error');
            state.retryCount++;

            if (state.retryCount < CONFIG.MAX_RETRIES) {
                log(`将在 2 秒后重试 (${state.retryCount}/${CONFIG.MAX_RETRIES})...`, 'info');
                setTimeout(() => {
                    state.isProcessing = false;
                    processCaptcha();
                }, 2000);
            } else {
                log('已达到最大重试次数', 'error');
                state.retryCount = 0;
            }
        } finally {
            if (state.retryCount === 0) {
                state.isProcessing = false;
            }
        }
    }

    // 监听错误消息
    function watchErrorMessage() {
        const errorElement = getElementByXPath(SELECTORS.ERROR_MESSAGE);
        if (!errorElement) return;

        // 创建 MutationObserver 监听错误消息变化
        if (state.observer) {
            state.observer.disconnect();
        }

        state.observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList' || mutation.type === 'characterData') {
                    const errorText = errorElement.textContent.trim();
                    if (errorText && errorText.length > 0) {
                        log(`检测到错误消息: ${errorText}`, 'info');
                        log('重新识别验证码...', 'info');
                        
                        // 重置状态
                        state.lastCaptchaUrl = null;
                        state.retryCount = 0;
                        
                        // 延迟一下，等待验证码图片刷新
                        setTimeout(() => {
                            processCaptcha();
                        }, 1000);
                    }
                }
            });
        });

        state.observer.observe(errorElement, {
            childList: true,
            characterData: true,
            subtree: true
        });

        log('已开始监听错误消息', 'debug');
    }

    // 初始化
    async function init() {
        log('脚本已加载', 'info');

        // 检查是否在登录页面
        if (!window.location.href.includes('login')) {
            log('不在登录页面，脚本待命', 'debug');
            return;
        }

        try {
            // 等待密码标签出现
            log('等待密码登录标签...', 'info');
            const passwordTab = await waitForElement(SELECTORS.PASSWORD_TAB, 5000);
            
            // 点击切换到密码登录
            log('点击切换到密码登录...', 'info');
            passwordTab.click();

            // 等待验证码图片出现
            log('等待验证码图片加载...', 'info');
            await waitForElement(SELECTORS.CAPTCHA_IMAGE, 5000);

            // 等待一下确保页面稳定
            await new Promise(resolve => setTimeout(resolve, 1000));

            // 开始监听错误消息
            watchErrorMessage();

            // 开始识别验证码
            await processCaptcha();

            // 定期检查验证码是否需要重新识别
            setInterval(() => {
                const captchaImg = getElementByXPath(SELECTORS.CAPTCHA_IMAGE);
                const captchaInput = getElementByXPath(SELECTORS.CAPTCHA_INPUT);
                
                // 如果验证码图片存在且输入框为空，则重新识别
                if (captchaImg && captchaInput && !captchaInput.value) {
                    log('检测到验证码输入框为空，重新识别...', 'debug');
                    state.lastCaptchaUrl = null;
                    processCaptcha();
                }
            }, 5000);

        } catch (error) {
            log(`初始化失败: ${error.message}`, 'error');
        }
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // 监听 URL 变化（SPA 应用）
    let lastUrl = location.href;
    new MutationObserver(() => {
        const url = location.href;
        if (url !== lastUrl) {
            lastUrl = url;
            log('URL 已变化，重新初始化...', 'debug');
            setTimeout(init, 1000);
        }
    }).observe(document, { subtree: true, childList: true });

    log('验证码自动识别脚本已就绪', 'success');
})();
