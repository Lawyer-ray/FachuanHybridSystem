// ==UserScript==
// @name         启信宝企业信息提取器
// @namespace    http://tampermonkey.net/
// @version      2.0
// @description  提取启信宝企业信息并生成易读的文本格式
// @author       fachuan (优化版)
// @match        https://www.qixin.com/company/*
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    // 等待页面加载完成的更可靠方式
    function waitForElement(selector, timeout = 10000) {
        return new Promise((resolve) => {
            const startTime = Date.now();

            const checkElement = () => {
                const element = document.evaluate(selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (element) {
                    resolve(element);
                } else if (Date.now() - startTime > timeout) {
                    resolve(null); // 超时返回null
                } else {
                    setTimeout(checkElement, 100); // 每100ms检查一次
                }
            };

            checkElement();
        });
    }

    // 主提取逻辑
    async function extractCompanyInfo() {
        try {
            // 提取企业名称
            const nameElement = await waitForElement('//*[@id="__nuxt"]/div/div[1]/div[2]/div[3]/div[1]/div[2]/div[1]/div/h1/span');
            const name = nameElement ? nameElement.textContent.trim() : '未获取到';

            // 提取统一社会信用代码
            const idNumberElement = await waitForElement('//*[@id="__nuxt"]/div/div[1]/div[2]/div[3]/div[2]/div[1]/div/div[1]/div[1]/div[1]/div[4]/div/span[1]');
            const id_number = idNumberElement ? idNumberElement.textContent.trim() : '未获取到';

            // 提取法定代表人
            const legalRepElement = await waitForElement('//*[@id="__nuxt"]/div/div[1]/div[2]/div[3]/div[2]/div[1]/div/div[1]/div[1]/div[1]/div[1]/div/div[1]/span/span/span/a');
            const legal_representative = legalRepElement ? legalRepElement.textContent.trim() : '未获取到';

            // 提取联系电话
            const phoneElement = await waitForElement('//*[@id="__nuxt"]/div/div[1]/div[2]/div[3]/div[2]/div[1]/div[1]/div[1]/div/div[2]/div[1]/div/div/span[1]/span');
            const phone = phoneElement ? phoneElement.textContent.trim() : '未获取到';

            // 提取注册地址
            let address = '未获取到';
            const tbodyElement = await waitForElement('//*[@id="rc-tabs-0-panel-gs"]/table/tbody');

            if (tbodyElement) {
                const trElements = tbodyElement.getElementsByTagName('tr');
                for (let tr of trElements) {
                    const tdElements = tr.getElementsByTagName('td');
                    if (tdElements.length >= 2) {
                        const firstTdText = tdElements[0].textContent.trim();
                        if (firstTdText.includes('注册地址')) {
                            const addressSpan = tdElements[1].querySelector('span');
                            address = addressSpan ? addressSpan.textContent.trim() : tdElements[1].textContent.trim();
                            break;
                        }
                    }
                }
            }

            // 构建纯文本格式
            const companyText = `名称: ${name}
类型: 法人
法定代表人：${legal_representative}
统一社会信用代码: ${id_number}
地址: ${address}
联系电话: ${phone}`;

            // 在控制台打印
            console.log('企业信息：');
            console.log(companyText);

            // 创建复制按钮
            createCopyButton(companyText);

        } catch (error) {
            console.error('提取企业信息时出错：', error);
            alert('提取企业信息失败，请刷新页面重试！');
        }
    }

    // 创建复制按钮
    function createCopyButton(textToCopy) {
        // 先检查是否已有按钮，避免重复创建
        const existingButton = document.querySelector('#qixin-copy-button');
        if (existingButton) {
            existingButton.remove();
        }

        const copyButton = document.createElement('button');
        copyButton.id = 'qixin-copy-button';
        copyButton.textContent = '复制企业信息';
        copyButton.style.cssText = `
            position: fixed;
            top: 10px;
            right: 10px;
            padding: 12px 20px;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            z-index: 9999;
            font-size: 14px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            transition: background-color 0.3s;
        `;

        // 悬停效果
        copyButton.addEventListener('mouseover', () => {
            copyButton.style.backgroundColor = '#45a049';
        });

        copyButton.addEventListener('mouseout', () => {
            copyButton.style.backgroundColor = '#4CAF50';
        });

        // 复制功能
        copyButton.addEventListener('click', async () => {
            try {
                // 使用现代的Clipboard API
                await navigator.clipboard.writeText(textToCopy);

                // 反馈复制成功
                copyButton.textContent = '已复制 ✔';
                copyButton.style.backgroundColor = '#2E7D32';

                // 恢复按钮文本
                setTimeout(() => {
                    copyButton.textContent = '复制企业信息';
                    copyButton.style.backgroundColor = '#4CAF50';
                }, 2000);

            } catch (err) {
                // 降级使用旧方法
                const textArea = document.createElement('textarea');
                textArea.value = textToCopy;
                document.body.appendChild(textArea);
                textArea.select();

                try {
                    document.execCommand('copy');
                    copyButton.textContent = '已复制 ✔';
                    copyButton.style.backgroundColor = '#2E7D32';
                    setTimeout(() => {
                        copyButton.textContent = '复制企业信息';
                        copyButton.style.backgroundColor = '#4CAF50';
                    }, 2000);
                } catch (fallbackErr) {
                    alert('复制失败，请手动复制！');
                    console.error('复制失败：', fallbackErr);
                } finally {
                    document.body.removeChild(textArea);
                }
            }
        });

        document.body.appendChild(copyButton);
    }

    // 启动提取
    extractCompanyInfo();

})();
