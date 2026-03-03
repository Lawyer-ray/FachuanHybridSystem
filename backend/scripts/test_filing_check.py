"""
用 CourtZxfwService + CourtZxfwFilingService 测试一张网立案
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.apiSystem.settings")

import django
django.setup()

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ACCOUNT = "18924051453"
PASSWORD = "532121wsN"


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        # 1. 登录（用 CourtZxfwService）
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

        svc = CourtZxfwService(page=page, context=ctx)
        result = svc.login(account=ACCOUNT, password=PASSWORD, max_captcha_retries=5, save_debug=True)
        logger.info("登录结果: %s", result)

        if not result.get("success"):
            logger.error("登录失败")
            browser.close()
            return

        # 2. 用 CourtZxfwFilingService 测试立案
        from apps.automation.services.scraper.sites.court_zxfw_filing import CourtZxfwFilingService

        filing = CourtZxfwFilingService(page=svc.page, save_debug=True)

        # 测试数据：多原告(法人+自然人)、多被告(法人+自然人)、第三人、两个代理人
        case_data = {
            "court_name": "广州市天河区人民法院",
            "cause_of_action": "买卖合同纠纷",
            "target_amount": "100000",
            "plaintiffs": [
                {
                    "type": "legal",
                    "name": "广州测试科技有限公司",
                    "uscc": "91440101MA5CTEST01",
                    "legal_rep": "张三",
                    "address": "广州市天河区测试路1号",
                    "phone": "13800000001",
                },
                {
                    "type": "natural",
                    "name": "李四",
                    "id_number": "440106199001011234",
                    "gender": "男",
                    "address": "广州市越秀区测试路2号",
                    "phone": "13800000002",
                },
            ],
            "defendants": [
                {
                    "type": "legal",
                    "name": "深圳被告实业有限公司",
                    "uscc": "91440101MA5CTEST02",
                    "legal_rep": "王五",
                    "address": "深圳市南山区测试路3号",
                    "phone": "13800000003",
                },
                {
                    "type": "natural",
                    "name": "赵六",
                    "id_number": "440106199201021234",
                    "gender": "女",
                    "address": "深圳市福田区测试路4号",
                    "phone": "13800000004",
                },
            ],
            "third_parties": [
                {
                    "type": "natural",
                    "name": "孙七",
                    "id_number": "440106199301031234",
                    "gender": "男",
                    "address": "佛山市禅城区测试路5号",
                    "phone": "13800000005",
                },
            ],
        }

        try:
            result = filing.file_case(case_data)
            logger.info("立案结果: %s", result)
        except Exception as e:
            logger.error("立案失败: %s", e, exc_info=True)

        input("\n按回车关闭浏览器...")
        browser.close()


if __name__ == "__main__":
    main()
