(function($) {
    'use strict';

    $(document).ready(function() {
        console.log('InboxMessage admin JS loaded');

        // 移动"提交到短信处理"按钮到 submit-row
        var btn = document.getElementById('submit-to-sms-btn');
        console.log('Button found:', btn);

        if (btn) {
            var submitRow = document.querySelector('.submit-row');
            console.log('Submit row found:', submitRow);

            if (submitRow) {
                // 先移动按钮到 submit-row
                submitRow.insertBefore(btn, submitRow.firstChild);
                // 然后隐藏原来的字段容器
                var fieldWrapper = btn.closest('.field-submit_to_sms_button');
                if (fieldWrapper) {
                    fieldWrapper.style.display = 'none';
                }
                console.log('Button moved successfully');
            }
        }
    });
})(django.jQuery);
