import time

from playwright.sync_api import sync_playwright


def capture_case_edit_page() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        page.goto("http://127.0.0.1:8002/admin/login/")
        page.wait_for_load_state("networkidle")

        page.fill('input[name="username"]', "黄崧")
        page.fill('input[name="password"]', "1234qwer")
        page.click('input[type="submit"]')
        page.wait_for_load_state("networkidle")

        page.goto("http://127.0.0.1:8002/admin/cases/case/7/change/")
        page.wait_for_load_state("networkidle")

        time.sleep(2)

        page.screenshot(path="tests/screenshots/case_edit_before.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    capture_case_edit_page()
