"""
司法送达网 (sfpt.cdfy12368.gov.cn) 文书下载爬虫

流程（纯 Playwright）：
1. 访问短链接 → 自动重定向到 pc.html?tdhParams=xxx
2. 等待页面加载，自动调用 getLinkInfo.do 获取链接信息
3. 在验证码输入框中输入验证码 → 调用 Vue 实例的 checkYzm() 验证
4. 验证成功后获取文书列表（wsList）
5. 逐个下载文书：singleDownload.do → downloadFileByFileIdAndLimit.do
6. 保存文件到本地

注意：所有 POST 请求参数都经过 TDHCryptoUtil 加密，无法通过纯 HTTP 复现，
因此只支持 Playwright 链路。
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from .base_court_scraper import BaseCourtDocumentScraper

logger = logging.getLogger("apps.automation")


class SfdwCourtScraper(BaseCourtDocumentScraper):
    """司法送达网 (sfpt.cdfy12368.gov.cn) 文书下载爬虫"""

    # 页面加载等待时间（毫秒）
    _PAGE_LOAD_WAIT_MS = 5000
    # 验证后等待时间（毫秒）
    _VERIFY_WAIT_MS = 5000
    # 下载等待时间（毫秒）
    _DOWNLOAD_WAIT_MS = 3000

    def run(self) -> dict[str, Any]:
        """执行文书下载任务"""
        logger.info("开始处理司法送达网链接: %s", self.task.url)

        download_dir = self._prepare_download_dir()

        # 获取验证码
        verification_code = self._get_verification_code()
        if not verification_code:
            raise ValueError("司法送达网链接需要验证码，但未找到验证码")

        logger.info("司法送达网: 获取到验证码")

        # 导航到目标页面
        self.navigate_to_url(timeout=30000)
        assert self.page is not None
        self.page.wait_for_timeout(self._PAGE_LOAD_WAIT_MS)

        # 输入验证码并确认
        self._input_verification_code(verification_code)
        self.page.wait_for_timeout(self._VERIFY_WAIT_MS)

        # 获取文书列表
        ws_list = self._get_ws_list()
        if not ws_list:
            self._save_page_state("sfdw_no_ws_list")
            raise ValueError("司法送达网: 验证后未获取到文书列表")

        logger.info("司法送达网: 获取到 %d 份文书", len(ws_list))

        # 下载文书
        files = self._download_all_documents(ws_list, download_dir)

        if not files:
            self._save_page_state("sfdw_no_downloads")
            raise ValueError("司法送达网: 未下载到任何文书")

        return {
            "source": "sfpt.cdfy12368.gov.cn",
            "mode": "playwright",
            "files": files,
            "downloaded_count": len(files),
            "failed_count": len(ws_list) - len(files),
            "message": f"司法送达网下载成功: {len(files)} 份",
        }

    # ==================== 验证码管理 ====================

    def _get_verification_code(self) -> str:
        """从任务配置中获取司法送达网验证码"""
        task_config = self.task.config if isinstance(self.task.config, dict) else {}
        code = str(task_config.get("sfdw_verification_code", "")).strip()
        return code

    # ==================== 验证码输入与验证 ====================

    def _input_verification_code(self, code: str) -> None:
        """输入验证码并触发验证

        司法送达网页面使用 Vue 实例管理状态：
        - input#checkCode 是验证码输入框
        - app.checkYzm() 是验证方法
        """
        assert self.page is not None

        # 在验证码输入框中输入
        check_code_input = self.page.locator("#checkCode")
        if check_code_input.count() == 0:
            self.screenshot("sfdw_no_checkcode_input")
            raise ValueError("司法送达网: 未找到验证码输入框 #checkCode")

        check_code_input.first.click(force=True, timeout=5000)
        check_code_input.first.fill("")
        check_code_input.first.fill(code)
        logger.info("司法送达网: 已输入验证码")

        self.page.wait_for_timeout(500)

        # 通过 JS 调用 Vue 实例的 checkYzm 方法
        result = self.page.evaluate("""() => {
            try {
                if (typeof app !== 'undefined' && app.checkYzm) {
                    app.checkYzm();
                    return 'called app.checkYzm()';
                }
                return 'app.checkYzm not found';
            } catch(e) {
                return 'error: ' + e.message;
            }
        }""")
        logger.info("司法送达网: 验证码提交结果: %s", result)

        # 等待验证完成
        self.page.wait_for_timeout(self._VERIFY_WAIT_MS)

    # ==================== 文书列表获取 ====================

    def _get_ws_list(self) -> list[dict[str, Any]]:
        """获取验证后的文书列表

        从 Vue 实例的 wsList 数据中获取文书信息。
        每个 wsList 项包含：
        - wjmc: 文件名称
        - wjgs: 文件格式（pdf等）
        - sdjzwjid: 文件ID
        """
        assert self.page is not None

        vue_data_str = self.page.evaluate("""() => {
            try {
                if (typeof app === 'undefined') return '{}';
                return JSON.stringify(app.$data);
            } catch(e) {
                return '{}';
            }
        }""")

        import json

        try:
            vue_data = json.loads(vue_data_str)
        except (json.JSONDecodeError, TypeError):
            logger.warning("司法送达网: 解析 Vue 数据失败")
            return []

        is_verified = vue_data.get("isVerified", False)
        if not is_verified:
            logger.warning("司法送达网: 验证码校验未通过 (isVerified=False)")

        ws_list = vue_data.get("wsList", [])
        if not isinstance(ws_list, list):
            ws_list = []

        # 提取案件信息用于日志
        ah = vue_data.get("ah", "")
        fymc = vue_data.get("fymc", "")
        if ah or fymc:
            logger.info("司法送达网: 案号=%s, 法院=%s", ah, fymc)

        return ws_list

    # ==================== 文书下载 ====================

    def _download_all_documents(self, ws_list: list[dict[str, Any]], download_dir: Path) -> list[str]:
        """逐个下载所有文书

        使用 Vue 实例的 downloadFile 方法触发下载。
        每次下载后等待文件保存完成。

        Args:
            ws_list: 文书列表
            download_dir: 下载目录

        Returns:
            下载成功的文件路径列表
        """
        assert self.page is not None
        files: list[str] = []

        for i, ws in enumerate(ws_list):
            wjmc = ws.get("wjmc", f"sfdw_doc_{i + 1}")
            wjgs = ws.get("wjgs", "pdf")
            doc_name = f"{wjmc}.{wjgs}" if not wjmc.endswith(f".{wjgs}") else wjmc

            logger.info("司法送达网: 下载第 %d/%d 个文书 (%s)", i + 1, len(ws_list), doc_name)

            filepath = self._download_single_document(ws, i, download_dir, doc_name)
            if filepath:
                files.append(filepath)

            # 下载间隔
            self.page.wait_for_timeout(1500)

        return files

    def _download_single_document(
        self, ws: dict[str, Any], index: int, download_dir: Path, doc_name: str
    ) -> str | None:
        """下载单个文书

        策略：
        1. 通过 JS 调用 downloadFile(app, ws) 触发下载
        2. 使用 Playwright expect_download 捕获下载事件
        3. 失败时尝试直接通过 API 链路下载

        Args:
            ws: 文书数据
            index: 文书索引
            download_dir: 下载目录
            doc_name: 文书名称

        Returns:
            下载文件路径，失败返回 None
        """
        assert self.page is not None

        # 策略1: 通过 Vue 方法触发下载
        try:
            import json

            ws_json = json.dumps(ws, ensure_ascii=False)
            with self.page.expect_download(timeout=30000) as download_info:
                self.page.evaluate(f"""(wsJson) => {{
                    try {{
                        const ws = JSON.parse(wsJson);
                        if (typeof downloadFile === 'function') {{
                            downloadFile(app, ws);
                            return 'called downloadFile';
                        }}
                        return 'downloadFile not found';
                    }} catch(e) {{
                        return 'error: ' + e.message;
                    }}
                }}""", ws_json)
            return self._save_download_file(download_info.value, download_dir, doc_name, index)
        except Exception as exc:
            logger.info("司法送达网: Vue downloadFile 方式下载失败，尝试备选方案: %s", exc)

        # 策略2: 监听网络请求，通过 JS 触发下载后拦截
        try:
            import json

            ws_json = json.dumps(ws, ensure_ascii=False)
            captured_downloads: list[Any] = []

            def on_download(download: Any) -> None:
                captured_downloads.append(download)

            self.page.on("download", on_download)

            self.page.evaluate(f"""(wsJson) => {{
                try {{
                    const ws = JSON.parse(wsJson);
                    if (typeof downloadFile === 'function') {{
                        downloadFile(app, ws);
                    }}
                }} catch(e) {{}}
            }}""", ws_json)

            # 等待下载事件
            for _ in range(30):
                if captured_downloads:
                    break
                self.page.wait_for_timeout(1000)

            self.page.remove_listener("download", on_download)

            if captured_downloads:
                return self._save_download_file(captured_downloads[0], download_dir, doc_name, index)

        except Exception as exc:
            logger.warning("司法送达网: 备选下载方案也失败: %s", exc)

        logger.warning("司法送达网: 文书 %s 下载失败", doc_name)
        return None

    def _save_download_file(
        self, download: Any, download_dir: Path, doc_name: str, index: int
    ) -> str:
        """保存下载文件

        Args:
            download: Playwright Download 对象
            download_dir: 下载目录
            doc_name: 文书名称
            index: 文书索引

        Returns:
            保存的文件路径
        """
        suggested = download.suggested_filename or ""
        if doc_name and (doc_name.endswith(".pdf") or doc_name.endswith(".doc")):
            filename = self._safe_filename(doc_name)
        elif suggested:
            filename = self._safe_filename(suggested)
        else:
            filename = f"sfdw_doc_{index}_{int(time.time())}.pdf"

        filepath = download_dir / filename
        download.save_as(str(filepath))
        logger.info("司法送达网: 下载成功: %s", filepath)
        return str(filepath)

    @staticmethod
    def _safe_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]+', "_", name).strip()
        return cleaned or f"sfdw_{int(time.time())}.pdf"
