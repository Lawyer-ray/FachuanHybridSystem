/**
 * 落位槽位 select2 候选渲染增强
 *
 * admin 原生初始化不暴露 templateResult 钩子，这里在 select2 就绪后
 * destroy 并按相同 data-* 配置重初始化，把「名称 (key) · 分类」中的分类
 * 渲染成右侧胶囊徽标（候选与选中态均生效）。
 */
(function () {
    "use strict";

    function formatSlot(item) {
        if (!item.id) {
            return item.text; // placeholder / 空选项
        }
        var idx = item.text.lastIndexOf(" \u00b7 "); // " · "
        if (idx === -1) {
            return item.text;
        }
        var jq = window.django ? window.django.jQuery : window.jQuery;
        return jq("<span>")
            .text(item.text.slice(0, idx))
            .append(jq("<span>").addClass("fc-slot-cat").text(item.text.slice(idx + 3)));
    }

    function enhance() {
        var jq = window.django ? window.django.jQuery : window.jQuery;
        if (!jq || !jq.fn || !jq.fn.select2) {
            return false;
        }
        var $el = jq("#id_folder_slot");
        if (!$el.length || !$el.data("select2")) {
            return false; // select2 尚未就绪
        }
        if ($el.data("fcSlotEnhanced")) {
            return true;
        }
        $el.data("fcSlotEnhanced", true);
        $el.select2("destroy");
        $el.select2({
            theme: "admin-autocomplete",
            width: "style",
            language: "zh-CN",
            allowClear: String($el.data("allow-clear")) === "true",
            placeholder: $el.data("placeholder") || "",
            templateResult: formatSlot,
            templateSelection: formatSlot,
            // ajax 配置由 select 元素上的 data-ajax--* 属性自动带入
        });
        return true;
    }

    function boot() {
        var tries = 0;
        (function tick() {
            if (enhance()) {
                return;
            }
            if (++tries > 40) {
                return;
            }
            setTimeout(tick, 100);
        })();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
