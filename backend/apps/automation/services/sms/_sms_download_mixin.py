"""短信下载任务管理 Mixin"""

import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from apps.automation.models import CourtSMS, CourtSMSStatus, ScraperTask, ScraperTaskStatus, ScraperTaskType
from apps.core.tasking import submit_task

logger = logging.getLogger("apps.automation")


class SMSDownloadMixin:
    """负责下载任务创建和等待状态检查"""

    HBFY_ACCOUNT_PATTERN = re.compile(r"账号\s*([0-9]{15,20})")
    HBFY_PASSWORD_PATTERN = re.compile(r"默认密码[：:]\s*([0-9A-Za-z]+)")
    SFDW_VERIFICATION_CODE_PATTERN = re.compile(r"验证码[：:]\s*(\w{4,6})")
    SFDW_GUANGXI_HOST = "171.106.48.55:28083"

    @classmethod
    def _normalize_phone_tail6(cls, raw: str | None) -> str | None:
        digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
        return digits[-6:] if len(digits) >= 6 else None

    @classmethod
    def _host_equals_or_subdomain(cls, host: str, domain: str) -> bool:
        return host == domain or host.endswith(f".{domain}")

    @classmethod
    def _is_sfdw_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
        return (
            cls._host_equals_or_subdomain(host, "sfpt.cdfy12368.gov.cn")
            or (host == "171.106.48.55" and parsed.port == 28083)
            or "/sfsdw//r/" in path
        )

    @classmethod
    def _is_jysd_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
        query = parse_qs(parsed.query)
        return cls._host_equals_or_subdomain(host, "jysd.10102368.com") or (path.endswith("/sd") and "key" in query)

    @classmethod
    def _is_hbfy_account_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
        return (cls._host_equals_or_subdomain(host, "dzsd.hbfy.gov.cn") and path.endswith("/sfsddz")) or path.endswith(
            "/sfsddz"
        )

    @classmethod
    def _is_zxfw_url(cls, url: str) -> bool:
        """判断是否为一张网链接（纯 API 可用，不依赖 Playwright）"""
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return cls._host_equals_or_subdomain(host, "zxfw.court.gov.cn")

    @classmethod
    def _get_required_platform_name(cls, url: str) -> str | None:
        """获取 URL 对应的平台名称，如果该平台需要 Playwright 则返回名称，否则返回 None。

        一张网(zxfw)支持纯 API 模式，不需要 Playwright，返回 None。
        其他平台都需要 Playwright，返回平台中文名。
        """
        if cls._is_zxfw_url(url):
            return None  # 一张网支持纯 API，不强制要求 Playwright
        if cls._is_hbfy_account_url(url):
            return "湖北电子送达"
        if cls._is_jysd_url(url):
            return "简易送达"
        if cls._is_sfdw_url(url):
            return "司法送达网"
        # 检查广东电子送达
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if cls._host_equals_or_subdomain(host, "sd.gdems.com"):
            return "广东电子送达"
        # 未知平台，保守地不要求 Playwright（后续结构探测时会检查）
        return None

    @classmethod
    def _is_playwright_available(cls) -> bool:
        """检查 Playwright 是否已安装"""
        try:
            import playwright

            return True
        except ImportError:
            return False

    def _collect_lawyer_phone_tail6_candidates(self, sms: CourtSMS) -> list[str]:
        """基于现有律师手机号优先级，提取后6位候选并去重。"""
        tails: list[str] = []
        seen: set[str] = set()

        for phone in self._collect_lawyer_phones(sms):
            tail = self._normalize_phone_tail6(phone)
            if tail and tail not in seen:
                seen.add(tail)
                tails.append(tail)

        return tails

    def _extract_hbfy_credentials(self, content: str) -> tuple[str | None, str | None]:
        account_match = self.HBFY_ACCOUNT_PATTERN.search(content)
        password_match = self.HBFY_PASSWORD_PATTERN.search(content)
        account = account_match.group(1).strip() if account_match else None
        password = password_match.group(1).strip() if password_match else None
        return account, password

    def _extract_sfdw_verification_code(self, content: str) -> str | None:
        code_match = self.SFDW_VERIFICATION_CODE_PATTERN.search(content)
        return code_match.group(1).strip() if code_match else None

    def _collect_lawyer_phones(self, sms: CourtSMS) -> list[str]:
        """收集律师手机号列表，优先发起任务律师，再所有律师。

        简易送达链接需要用律师手机号登录，按优先级排列：
        1. 关联案件的承办律师（通过 assignment）
        2. 管理员律师
        3. 所有有手机号的律师
        """
        phones: list[str] = []
        seen: set[str] = set()

        def _add_phone(phone: str) -> None:
            cleaned = phone.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                phones.append(cleaned)

        # 优先从关联案件获取承办律师手机号
        if sms.case:
            try:
                from apps.cases.models import CaseAssignment

                for assignment in CaseAssignment.objects.select_related("lawyer").filter(case=sms.case).order_by("id"):
                    lawyer = assignment.lawyer
                    phone = str(getattr(lawyer, "phone", "") or "").strip()
                    if phone:
                        _add_phone(phone)
            except Exception as exc:
                logger.warning(f"短信 {sms.id} 获取案件承办律师失败: {exc}")

        # 补充管理员律师
        try:
            from apps.core.interfaces import ServiceLocator

            lawyer_service = ServiceLocator.get_lawyer_service()
            admin_lawyer = lawyer_service.get_admin_lawyer()
            if admin_lawyer and admin_lawyer.phone:
                _add_phone(admin_lawyer.phone)
        except Exception as exc:
            logger.warning(f"短信 {sms.id} 获取管理员律师失败: {exc}")

        # 最后补充所有有手机号的律师
        try:
            from apps.organization.models import Lawyer

            for lawyer in Lawyer.objects.exclude(phone__isnull=True).exclude(phone="").order_by("id"):
                _add_phone(str(lawyer.phone).strip())
        except Exception as exc:
            logger.warning(f"短信 {sms.id} 获取全部律师手机号失败: {exc}")

        return phones

    def _create_download_task(
        self,
        sms: CourtSMS,
        process_options: dict[str, Any] | None = None,
    ) -> ScraperTask | None:
        """创建下载任务并关联到短信记录，然后提交到 Django Q 队列执行"""
        if not sms.download_links:
            return None

        try:
            download_url = sms.download_links[0]

            # 检查该 URL 是否需要 Playwright，若需要但未安装则直接标记失败
            platform_name = self._get_required_platform_name(download_url)
            if platform_name and not self._is_playwright_available():
                error_msg = (
                    f"「{platform_name}」平台需要 Playwright 浏览器支持，"
                    "但 Playwright 未安装。请运行: uv add playwright && playwright install chromium"
                )
                logger.warning(f"短信 {sms.id} 跳过下载任务创建: {error_msg}")
                # 创建一个失败状态的任务，让流程继续而非卡住
                task = ScraperTask.objects.create(
                    task_type=ScraperTaskType.COURT_DOCUMENT,
                    url=download_url,
                    case=sms.case,
                    config={"court_sms_id": sms.id, "auto_download": True, "source": "court_sms"},
                    status=ScraperTaskStatus.FAILED,
                    error_message=error_msg,
                )
                return task

            task_config: dict[str, Any] = {"court_sms_id": sms.id, "auto_download": True, "source": "court_sms"}

            if self._is_hbfy_account_url(download_url):
                account, password = self._extract_hbfy_credentials(sms.content)
                if account and password:
                    logger.info(f"短信 {sms.id} 提取到湖北账号模式凭证，将在下载阶段临时使用（不落库）")
                else:
                    logger.warning(f"短信 {sms.id} 为湖北账号模式但未提取到完整凭证")

            if self._is_jysd_url(download_url):
                lawyer_phones = self._collect_lawyer_phones(sms)
                if lawyer_phones:
                    task_config["jysd_lawyer_phones"] = lawyer_phones
                    logger.info(f"短信 {sms.id} 为简易送达链接，注入 {len(lawyer_phones)} 个律师手机号")
                else:
                    logger.warning(f"短信 {sms.id} 为简易送达链接但未找到律师手机号")

            if self._is_sfdw_url(download_url):
                verification_code = self._extract_sfdw_verification_code(sms.content)
                if verification_code:
                    task_config["sfdw_verification_code"] = verification_code
                    logger.info(f"短信 {sms.id} 为司法送达网链接，注入验证码")

                manual_tail6 = self._normalize_phone_tail6(
                    process_options.get("sfdw_phone_tail6") if isinstance(process_options, dict) else None
                )
                if manual_tail6:
                    task_config["sfdw_phone_tail6"] = manual_tail6
                    logger.info(f"短信 {sms.id} 为司法送达网链接，注入手工手机号后6位")
                else:
                    tail_candidates = self._collect_lawyer_phone_tail6_candidates(sms)
                    if tail_candidates:
                        task_config["sfdw_phone_tail6_candidates"] = tail_candidates
                        logger.info(
                            "短信 %s 为司法送达网链接，注入 %s 个律师手机号后6位候选",
                            sms.id,
                            len(tail_candidates),
                        )
                    else:
                        logger.warning(f"短信 {sms.id} 为司法送达网链接但未找到可用手机号后6位")

            task = ScraperTask.objects.create(
                task_type=ScraperTaskType.COURT_DOCUMENT,
                url=download_url,
                case=sms.case,
                config=task_config,
            )

            logger.info(f"创建下载任务成功: Task ID={task.id}, URL={download_url}")

            queue_task_id = submit_task(
                "apps.automation.tasks.execute_scraper_task", task.id, task_name=f"court_document_download_{task.id}"
            )

            logger.info(f"提交下载任务到队列: Task ID={task.id}, Queue Task ID={queue_task_id}")

            return task

        except Exception as e:
            logger.error(f"创建下载任务失败: SMS ID={sms.id}, 错误: {e!s}")
            return None

    def _should_wait_for_document_download(self, sms: CourtSMS) -> bool:
        """检查是否需要等待文书下载完成后再进行匹配"""
        try:
            if sms.party_names or not sms.download_links or not sms.scraper_task:
                return False

            fresh_task = self._refresh_scraper_task(sms)
            if fresh_task is None:
                return False

            if fresh_task.status in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
                self._log_completed_task_files(sms, fresh_task)
                return False

            if not hasattr(fresh_task, "documents"):
                return fresh_task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]

            return self._check_documents_wait_status(sms, fresh_task)

        except Exception as e:
            logger.error(f"检查下载状态失败: SMS ID={sms.id}, 错误: {e!s}")
            return False

    def _refresh_scraper_task(self, sms: CourtSMS) -> Any:
        """刷新并返回最新的 ScraperTask，不存在则返回 None"""
        try:
            if sms.scraper_task is None:
                return None
            fresh_task = ScraperTask.objects.get(id=sms.scraper_task.id)
            sms.scraper_task = fresh_task
            logger.info(f"短信 {sms.id} 刷新下载任务状态: {fresh_task.status}")
            return fresh_task
        except Exception:
            logger.warning(f"短信 {sms.id} 的下载任务不存在，无需等待")
            return None

    def _log_completed_task_files(self, sms: CourtSMS, task: Any) -> None:
        """记录已完成任务的文件信息"""
        logger.info(f"短信 {sms.id} 的下载任务已完成（状态: {task.status}），不再等待")
        if task.result and isinstance(task.result, dict):
            files = task.result.get("files", [])
            if files:
                logger.info(f"短信 {sms.id} 从任务结果中发现 {len(files)} 个已下载文件")

    def _check_documents_wait_status(self, sms: CourtSMS, task: Any) -> bool:
        """根据文书记录状态判断是否需要等待"""
        all_docs = task.documents.all()
        if not all_docs.exists():
            running = task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]
            wait_msg = "需要" if running else "不再"
            running_msg = "进行中但" if running else ""
            logger.info(f"短信 {sms.id} 的下载任务{running_msg}没有文书记录，{wait_msg}等待")
            return running

        successful = all_docs.filter(download_status="success")
        pending = all_docs.filter(download_status="pending")
        downloading = all_docs.filter(download_status="downloading")

        logger.info(
            f"短信 {sms.id} 文书状态统计: 总数={all_docs.count()}, "
            f"成功={successful.count()}, 待下载={pending.count()}, 下载中={downloading.count()}"
        )

        if successful.exists():
            logger.info(f"短信 {sms.id} 已有下载成功的文书，可以进行匹配")
            return False

        if task.status in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
            logger.info(f"短信 {sms.id} 的下载任务已完成（状态: {task.status}），不再等待")
            return False

        if (
            task.status == ScraperTaskStatus.RUNNING
            and all_docs.count() > 0
            and successful.count() == 0
            and pending.count() == 0
            and downloading.count() == 0
        ):
            logger.info(f"短信 {sms.id} 的下载任务运行中但所有文书都已失败，不再等待")
            return False

        should_wait = (
            pending.exists()
            or downloading.exists()
            or task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]
        )
        logger.info(
            f"短信 {sms.id} {'还有文书在下载中或任务进行中，需要等待' if should_wait else '下载状态检查完成，无需等待'}"
        )
        return should_wait

    def handle_scraper_task_status_change(self, scraper_task: ScraperTask) -> None:
        """当 ScraperTask 状态变为 SUCCESS/FAILED 时，触发关联 SMS 的后续处理流程。

        此方法从 Model 层 @hook 薄调用，业务逻辑集中在 Service 层。
        """
        if scraper_task.status not in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
            return

        try:
            court_sms_records = CourtSMS.objects.filter(scraper_task=scraper_task)
            for sms in court_sms_records:
                if sms.status not in [CourtSMSStatus.DOWNLOADING, CourtSMSStatus.MATCHING]:
                    continue
                if scraper_task.status == ScraperTaskStatus.SUCCESS:
                    self._handle_sms_download_success(sms, scraper_task)
                elif scraper_task.status == ScraperTaskStatus.FAILED:
                    if self._handle_sms_download_failed(sms, scraper_task):
                        continue
        except Exception as e:
            logger.error(
                "❌ 处理下载完成信号失败: Task ID=%s, 错误: %s",
                scraper_task.id,
                e,
                extra={"action": "download_signal_failed", "task_id": scraper_task.id, "error": str(e)},
                exc_info=True,
            )

    def _handle_sms_download_success(self, sms: CourtSMS, scraper_task: ScraperTask) -> None:
        """处理下载成功的 SMS"""
        if sms.status == CourtSMSStatus.DOWNLOADING:
            sms.status = CourtSMSStatus.MATCHING
            sms.save()
            logger.info("✅ 下载任务完成，进入匹配阶段: SMS ID=%s, Task ID=%s", sms.id, scraper_task.id)
        elif sms.status == CourtSMSStatus.MATCHING:
            logger.info("✅ 下载任务完成，继续匹配流程: SMS ID=%s, Task ID=%s", sms.id, scraper_task.id)

        task_id = submit_task(
            "apps.automation.services.sms.court_sms_service.process_sms_async",
            sms.id,
            task_name=f"court_sms_continue_{sms.id}",
        )
        logger.info("提交后续处理任务: SMS ID=%s, Queue Task ID=%s", sms.id, task_id)

    def _handle_sms_download_failed(self, sms: CourtSMS, scraper_task: ScraperTask) -> bool:
        """处理下载失败的 SMS，返回是否需要 continue（跳过重试逻辑）"""
        if sms.status == CourtSMSStatus.MATCHING:
            logger.info("下载失败但继续匹配流程: SMS ID=%s", sms.id)
            task_id = submit_task(
                "apps.automation.services.sms.court_sms_service.process_sms_async",
                sms.id,
                task_name=f"court_sms_continue_after_download_failed_{sms.id}",
            )
            logger.info("下载失败后继续处理任务: SMS ID=%s, Queue Task ID=%s", sms.id, task_id)
            return True

        sms.status = CourtSMSStatus.DOWNLOAD_FAILED
        sms.error_message = scraper_task.error_message or "下载任务失败"
        sms.save()
        logger.warning(
            "⚠️ 下载任务失败: SMS ID=%s, Task ID=%s, 错误: %s",
            sms.id,
            scraper_task.id,
            scraper_task.error_message,
        )

        if sms.retry_count < 3:
            from datetime import timedelta

            from django.utils import timezone

            from apps.core.tasking import ScheduleQueryService

            next_run = timezone.now() + timedelta(seconds=60)
            ScheduleQueryService().create_once_schedule(
                func="apps.automation.services.sms.court_sms_service.retry_download_task",
                args=str(sms.id),
                name=f"court_sms_retry_download_{sms.id}",
                next_run=next_run,
            )
            logger.info("提交重试下载任务: SMS ID=%s, 计划执行时间=%s", sms.id, next_run)
        else:
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = f"下载失败，已重试{sms.retry_count}次"
            sms.save()
            logger.error("下载重试次数用完，标记为失败: SMS ID=%s", sms.id)
        return False

    def _process_downloading_or_matching(
        self,
        sms: CourtSMS,
        process_options: dict[str, Any] | None = None,
    ) -> CourtSMS:
        """根据是否有下载链接决定进入下载或匹配阶段"""
        if sms.download_links:
            logger.info(f"短信 {sms.id} 有下载链接，创建下载任务")
            scraper_task = self._create_download_task(sms, process_options=process_options)
            if scraper_task:
                sms.scraper_task = scraper_task
                sms.status = CourtSMSStatus.DOWNLOADING
                sms.save()
                logger.info(f"下载任务创建成功: SMS ID={sms.id}, Task ID={scraper_task.id}")
            else:
                logger.warning(f"下载任务创建失败，直接进入匹配: SMS ID={sms.id}")
                sms.status = CourtSMSStatus.MATCHING
                sms.save()
        else:
            logger.info(f"短信 {sms.id} 无下载链接，直接进入匹配")
            sms.status = CourtSMSStatus.MATCHING
            sms.save()

        return sms
