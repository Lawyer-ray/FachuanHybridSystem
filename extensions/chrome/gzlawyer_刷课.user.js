// ==UserScript==
// @name         广州律协刷课
// @namespace    https://oa.gzlawyer.org/
// @version      1.0.0
// @description  自动遍历课程列表，收集50个课程ID，依次打开并在70秒后关闭
// @author       FachuanAI
// @match        http://oa.gzlawyer.org/workbench/*
// @match        https://oa.gzlawyer.org/workbench/*
// @match        http://oa.gzlawyer.org/views/gam/paperCourse-mvc-view.jsp*
// @match        https://oa.gzlawyer.org/views/gam/paperCourse-mvc-view.jsp*
// @grant        GM_openInTab
// @grant        unsafeWindow
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const COURSE_URL = 'https://oa.gzlawyer.org/views/gam/paperCourse-mvc-view.jsp?id=';
    const TARGET_COUNT = 50;
    const TAB_CLOSE_DELAY = 70000;    // 70秒后统一关闭

    // ── 只在课程列表页注入按钮 ──────────────────────────────────────────
    function isListPage() {
        const hash = decodeURIComponent(location.hash);
        return hash.includes('gam.PaperCourse@mvc-list') || hash.includes('PaperCourse') && hash.includes('mvc-list');
    }

    function injectButton() {
        if (document.getElementById('gz-刷课-btn')) return;
        const btn = document.createElement('button');
        btn.id = 'gz-刷课-btn';
        btn.textContent = '🎓 开始上课';
        Object.assign(btn.style, {
            position: 'fixed', top: '12px', right: '16px', zIndex: 99999,
            padding: '8px 18px', background: '#1890ff', color: '#fff',
            border: 'none', borderRadius: '6px', cursor: 'pointer',
            fontSize: '14px', fontWeight: 'bold', boxShadow: '0 2px 8px rgba(0,0,0,.3)'
        });
        btn.addEventListener('click', startCourse);
        document.body.appendChild(btn);
    }

    // ── 采集 data-entityid ──────────────────────────────────────────────
    function collectCurrentPageIds() {
        return Array.from(document.querySelectorAll('input[data-entityid]'))
            .map(el => el.getAttribute('data-entityid'))
            .filter(Boolean);
    }

    // 等待翻页完成：等到 input[data-entityid] 的第一个值与 oldFirstId 不同
    function waitForPageChange(oldFirstId, timeout = 8000) {
        return new Promise((resolve, reject) => {
            const start = Date.now();
            const check = () => {
                const ids = collectCurrentPageIds();
                if (ids.length > 0 && ids[0] !== oldFirstId) return resolve(ids);
                if (Date.now() - start > timeout) return reject(new Error('翻页超时'));
                setTimeout(check, 300);
            };
            check();
        });
    }

    // ── 主流程 ─────────────────────────────────────────────────────────
    async function startCourse() {
        const btn = document.getElementById('gz-刷课-btn');
        btn.disabled = true;
        btn.textContent = '⏳ 采集中...';

        const collected = new Set();

        try {
            // 先采集当前页
            collectCurrentPageIds().forEach(id => collected.add(id));
            log(`第1页采集 ${collected.size} 个`);

            // 翻页直到够50个
            let page = 2;
            while (collected.size < TARGET_COUNT) {
                const oldFirstId = collectCurrentPageIds()[0];

                // 点击下一页
                const nextBtn = Array.from(document.querySelectorAll('ul.pagination a'))
                    .find(a => a.textContent.trim() === '下一页');
                if (!nextBtn) { log('没有下一页，停止'); break; }
                nextBtn.click();

                // 等待翻页完成
                const newIds = await waitForPageChange(oldFirstId).catch(() => []);
                if (newIds.length === 0) { log('翻页失败，停止'); break; }

                newIds.forEach(id => collected.add(id));
                log(`第${page}页采集，累计 ${collected.size} 个`);
                page++;

                await sleep(500); // 稍等，避免请求过快
            }

            const ids = Array.from(collected).slice(0, TARGET_COUNT);
            log(`共采集 ${ids.length} 个课程ID，开始打开标签...`);

            // 第一步：全部在后台打开
            const tabs = [];
            for (let i = 0; i < ids.length; i++) {
                const tab = GM_openInTab(COURSE_URL + ids[i], { active: false, insert: true });
                tabs.push(tab);
                btn.textContent = `📂 打开中 ${i + 1}/${ids.length}`;
                await sleep(300); // 稍微间隔，避免同时发起太多请求
            }

            log('全部打开完毕，开始逐个激活...');

            // 第二步：依次切换到每个标签激活一下，再切回来
            for (let i = 0; i < tabs.length; i++) {
                btn.textContent = `⚡ 激活中 ${i + 1}/${tabs.length}`;
                tabs[i].focus(); // 切换到该标签
                await sleep(1500); // 停留1.5秒确保激活
            }

            log(`全部激活完毕，${TAB_CLOSE_DELAY / 1000}秒后统一关闭`);
            btn.textContent = `⏳ 等待${TAB_CLOSE_DELAY / 1000}秒后关闭...`;

            // 第三步：等70秒后统一关闭
            await sleep(TAB_CLOSE_DELAY);
            tabs.forEach(tab => tab.close());

            btn.textContent = `✅ 全部完成，${ids.length} 个标签已关闭`;
            btn.disabled = false;
            log('全部课程完成');

        } catch (e) {
            log('出错: ' + e.message);
            btn.textContent = '❌ 出错，点击重试';
            btn.disabled = false;
        }
    }

    function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    function log(msg) {
        console.log('[广州律协刷课]', msg);
    }

    // ── 课程详情页：70秒后自动关闭 ─────────────────────────────────────
    function isCourseViewPage() {
        return location.pathname.includes('paperCourse-mvc-view.jsp');
    }

    if (isCourseViewPage()) {
        // 串行模式下由列表页控制关闭，此处无需操作
    } else {
        // ── 列表页：监听 hash 变化注入按钮 ──────────────────────────────
        window.addEventListener('hashchange', () => {
            if (isListPage()) setTimeout(injectButton, 1500);
        });

        // SPA 路由可能在脚本执行后才渲染，轮询等待 body 出现后再注入
        function tryInject(retries = 20) {
            if (isListPage() && document.body) {
                injectButton();
            } else if (retries > 0) {
                setTimeout(() => tryInject(retries - 1), 500);
            }
        }
        tryInject();
    }

})();
