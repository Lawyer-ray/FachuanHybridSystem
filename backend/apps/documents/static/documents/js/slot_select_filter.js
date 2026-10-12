/**
 * 落位槽位下拉过滤框
 *
 * 槽位词表 30+ 项，optgroup 分组后仍需滚动；在 select 上方注入搜索输入框，
 * 输入即过滤 option 与空组（保留分组结构）。纯原生 JS，无新依赖。
 */
(function () {
    "use strict";

    function init() {
        var select = document.getElementById("id_folder_slot");
        if (!select || select.dataset.slotFilterInit) {
            return;
        }
        select.dataset.slotFilterInit = "1";

        var input = document.createElement("input");
        input.type = "text";
        input.placeholder = "输入关键词过滤槽位（如：委托 / 送达）…";
        input.className = "vTextField";
        input.style.display = "block";
        input.style.marginBottom = "6px";
        input.setAttribute("aria-label", "过滤槽位");
        select.parentNode.insertBefore(input, select);

        var options = Array.prototype.slice.call(select.querySelectorAll("option"));

        input.addEventListener("input", function () {
            var query = input.value.trim().toLowerCase();
            var groupHasHit = new Map();

            options.forEach(function (option) {
                if (!option.value) {
                    // 空选项（— 未声明 —）：搜索时隐藏，清空后恢复
                    option.hidden = !!query;
                    return;
                }
                var hit = !query || option.textContent.toLowerCase().indexOf(query) !== -1;
                option.hidden = !hit;
                if (hit) {
                    var group = option.closest("optgroup");
                    if (group) {
                        groupHasHit.set(group, true);
                    }
                }
            });

            select.querySelectorAll("optgroup").forEach(function (group) {
                group.hidden = !groupHasHit.get(group);
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
