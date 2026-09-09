/*
 * 法穿 AI — Django Admin 移动端抽屉侧边栏开关
 *
 * 仅在 ≤767px 与 DOM 元素齐备时生效：
 *   - 点击 header 汉堡按钮（#fc-mobile-nav-toggle）开合抽屉
 *   - 点击遮罩 / Escape 关闭
 *   - 点击抽屉内导航链接后自动收起
 *
 * 抽屉可见性由 body.fc-mobile-nav-open 类驱动（见 mobile_nav_drawer.css），
 * 不读写 django.admin.navSidebarIsOpen，避免污染桌面端侧边栏状态。
 */
"use strict";
(function () {
    var MQ = "(max-width: 767px)";

    function init() {
        var toggle = document.getElementById("fc-mobile-nav-toggle");
        var sidebar = document.getElementById("nav-sidebar");
        if (!toggle || !sidebar || sidebar.dataset.fcMobileNavBound === "1") {
            return;
        }
        sidebar.dataset.fcMobileNavBound = "1";

        var mql = window.matchMedia(MQ);
        var backdrop = null;

        function isMobile() {
            return mql.matches;
        }

        function ensureBackdrop() {
            if (backdrop) {
                return backdrop;
            }
            backdrop = document.createElement("div");
            backdrop.className = "fc-mobile-nav-backdrop";
            backdrop.hidden = true;
            document.body.appendChild(backdrop);
            backdrop.addEventListener("click", close);
            return backdrop;
        }

        function syncBackdrop() {
            var bd = ensureBackdrop();
            var open = isMobile() &&
                document.body.classList.contains("fc-mobile-nav-open");
            bd.hidden = !open;
        }

        function open() {
            if (!isMobile()) {
                return;
            }
            document.body.classList.add("fc-mobile-nav-open");
            toggle.setAttribute("aria-expanded", "true");
            syncBackdrop();
        }

        function close() {
            document.body.classList.remove("fc-mobile-nav-open");
            toggle.setAttribute("aria-expanded", "false");
            syncBackdrop();
        }

        toggle.addEventListener("click", function () {
            if (document.body.classList.contains("fc-mobile-nav-open")) {
                close();
            } else {
                open();
            }
        });

        // 点击抽屉内任意导航链接后自动收起（页面即将跳转，收起避免残影）
        sidebar.addEventListener("click", function (event) {
            var target = event.target;
            if (target && target.closest && target.closest("a")) {
                close();
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                close();
            }
        });

        function handleMqlChange() {
            close();
        }

        if (typeof mql.addEventListener === "function") {
            mql.addEventListener("change", handleMqlChange);
        } else if (typeof mql.addListener === "function") {
            mql.addListener(handleMqlChange); // 旧版 Safari 兼容
        }

        // 初始化时若处于打开态但已切到桌面端，做一次兜底复位
        if (!isMobile()) {
            close();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
