import asyncio

from playwright.async_api import async_playwright


async def test_litigation_generation():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("http://127.0.0.1:8002/admin/login/")
        await page.wait_for_load_state("networkidle")
        await page.fill("#id_username", "黄崧")
        await page.fill("#id_password", "1234qwer")
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle")

        await page.goto("http://127.0.0.1:8002/admin/cases/case/6/change/")
        await page.wait_for_load_state("networkidle")

        btn = await page.query_selector('input[value="生成诉状"]')
        if not btn:
            await browser.close()
            return

        await btn.click()
        await asyncio.sleep(1)

        dialog = await page.query_selector("#litigation_type_dialog")
        if not dialog:
            await browser.close()
            return

        await asyncio.sleep(2)
        await page.screenshot(path="tests/screenshots/litigation_dialog.png")

        complaint_option = await page.query_selector('.litigation-type-option:has-text("起诉状")')
        if complaint_option:
            await complaint_option.click()
            await asyncio.sleep(0.5)

        generate_btn = await page.query_selector(".btn-generate")
        if generate_btn:
            async with page.expect_download() as download_info:
                await generate_btn.click()
            download = await download_info.value
            await download.save_as(f"tests/screenshots/{download.suggested_filename}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_litigation_generation())
