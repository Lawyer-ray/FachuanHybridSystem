"""
短信解析服务

负责解析法院短信内容，提取下载链接、案号、当事人等信息
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, cast
from urllib.parse import parse_qs, urlparse

from apps.automation.models import CourtSMSType
from apps.automation.utils.text_utils import TextUtils
from apps.core.interfaces import ServiceLocator
from apps.core.llm.config import LLMConfig
from apps.core.llm.exceptions import LLMError

if TYPE_CHECKING:
    from apps.core.interfaces import IClientService

logger = logging.getLogger("apps.automation")


@dataclass
class SMSParseResult:
    """短信解析结果"""

    sms_type: str
    download_links: list[str]
    case_numbers: list[str]
    party_names: list[str]
    has_valid_download_link: bool
    verification_code: str = ""


class SMSParserService:
    """短信解析服务"""

    # 下载链接正则（必须包含 qdbh、sdbh、sdsin 参数）
    # 支持同构异域名：只校验路径结构和必要参数，不绑定固定 host
    DOWNLOAD_LINK_PATTERN = re.compile(
        r"https?://[^\s/]+/zxfw/#/pagesAjkj/app/wssd/index\?"
        r"[^\s]*?(?=.*qdbh=[^\s&]+)(?=.*sdbh=[^\s&]+)(?=.*sdsin=[^\s&]+)[^\s]*",
        re.IGNORECASE,
    )

    # 广东电子送达链接正则
    # 格式: https://<任意域名>/v3/dzsd/xxxxx
    GDEMS_LINK_PATTERN = re.compile(r"https?://[^\s/]+/v3/dzsd/[a-zA-Z0-9]+", re.IGNORECASE)

    # 简易送达链接正则
    # 格式: https://<任意域名>/sd?key=xxxxx
    JYSD_LINK_PATTERN = re.compile(r"https?://[^\s/]+/sd\?key=[a-zA-Z0-9_\-]+", re.IGNORECASE)

    # 湖北电子送达链接正则
    # 1) 免账号短信链接: http(s)://<任意域名>/hb/msg=xxxx
    # 2) 账号密码入口: http(s)://<任意域名>/sfsddz
    HBFY_PUBLIC_LINK_PATTERN = re.compile(r"https?://[^\s/]+/hb/msg=[a-zA-Z0-9]+", re.IGNORECASE)
    HBFY_ACCOUNT_LINK_PATTERN = re.compile(r"https?://[^\s/]+/sfsddz\b", re.IGNORECASE)

    # 司法送达网链接正则
    # 格式: http(s)://<任意域名或IP[:端口]>/sfsdw//r/xxxxxx
    SFDW_LINK_PATTERN = re.compile(r"https?://[^\s/]+/sfsdw//r/[a-zA-Z0-9]+", re.IGNORECASE)

    # 通用 URL 候选提取（用于兜底识别）
    URL_CANDIDATE_PATTERN = re.compile(r"https?://[^\s<>'\"，。；;]+", re.IGNORECASE)
    # 司法送达网验证码正则
    # 格式: 验证码：xxxx
    SFDW_VERIFICATION_CODE_PATTERN = re.compile(r"验证码[：:]\s*(\w{4,6})")


    def __init__(
        self,
        ollama_model: str | None = None,
        ollama_base_url: str | None = None,
        llm_service: Any | None = None,
        client_service: Optional["IClientService"] = None,
        party_matching_service: object | None = None,
        party_candidate_extractor: object | None = None,
    ):
        """
        初始化SMS解析服务

        Args:
            ollama_model: Ollama模型名称，默认从配置文件读取
            ollama_base_url: Ollama服务地址，默认从配置文件读取
            client_service: 客户服务实例，用于依赖注入
            party_matching_service: 当事人匹配服务，用于依赖注入
            party_candidate_extractor: 当事人候选提取器，用于依赖注入
        """
        self._ollama_model = ollama_model
        self._ollama_base_url = ollama_base_url
        self._llm_service = llm_service
        self._client_service = client_service
        self._party_matching_service = party_matching_service
        self._party_candidate_extractor = party_candidate_extractor

    @property
    def ollama_model(self) -> str:
        """延迟加载 Ollama 模型配置，避免初始化阶段触发外部依赖。"""
        if self._ollama_model is None:
            self._ollama_model = LLMConfig.get_ollama_model()
        return self._ollama_model

    @property
    def ollama_base_url(self) -> str:
        """延迟加载 Ollama 服务地址配置。"""
        if self._ollama_base_url is None:
            self._ollama_base_url = LLMConfig.get_ollama_base_url()
        return self._ollama_base_url

    @property
    def llm_service(self) -> Any:
        if self._llm_service is None:
            self._llm_service = ServiceLocator.get_llm_service()
        return self._llm_service

    @property
    def client_service(self) -> "IClientService":
        """延迟加载客户服务"""
        if self._client_service is None:
            from apps.core.dependencies.automation_sms_wiring import build_sms_client_service

            self._client_service = build_sms_client_service()
        return self._client_service

    @property
    def party_matching_service(self) -> object:
        """延迟加载当事人匹配服务"""
        if self._party_matching_service is None:
            from apps.automation.services.sms.matching import _get_party_matching_service

            self._party_matching_service = _get_party_matching_service()
        return self._party_matching_service

    @property
    def party_candidate_extractor(self) -> object:
        """延迟加载当事人候选提取器"""
        if self._party_candidate_extractor is None:
            from apps.automation.services.sms.parsing import PartyCandidateExtractor

            self._party_candidate_extractor = PartyCandidateExtractor()
        return self._party_candidate_extractor

    def parse(self, content: str) -> SMSParseResult:
        """
        解析短信内容

        Args:
            content: 短信内容

        Returns:
            SMSParseResult: 解析结果
        """
        logger.info(f"开始解析短信内容，长度: {len(content)}")

        # 提取下载链接
        download_links = self.extract_download_links(content)
        has_valid_download_link = len(download_links) > 0

        # 提取案号
        case_numbers = self.extract_case_numbers(content)

        # 提取当事人名称
        party_names = self.extract_party_names(content)

        # 提取司法送达网验证码
        verification_code = self.extract_verification_code(content)

        # 判定短信类型
        if has_valid_download_link:
            sms_type = CourtSMSType.DOCUMENT_DELIVERY
        else:
            # 简单判断：如果包含"立案"关键词则为立案通知，否则为信息通知
            if "立案" in content:
                sms_type = CourtSMSType.FILING_NOTIFICATION
            else:
                sms_type = CourtSMSType.INFO_NOTIFICATION

        result = SMSParseResult(
            sms_type=sms_type,
            download_links=download_links,
            case_numbers=case_numbers,
            party_names=party_names,
            has_valid_download_link=has_valid_download_link,
            verification_code=verification_code,
        )

        logger.info(
            f"短信解析完成: 类型={sms_type}, 链接数={len(download_links)}, "
            f"案号数={len(case_numbers)}, 当事人数={len(party_names)}"
        )

        return result

    def extract_download_links(self, content: str) -> list[str]:
        """
        提取有效下载链接

        识别策略：
        1. 优先用平台特征正则提取（路径结构）
        2. 再用通用 URL 正则兜底
        3. 统一做链接清洗 + 平台规则校验

        Args:
            content: 短信内容

        Returns:
            List[str]: 有效下载链接列表
        """
        valid_links: list[str] = []
        seen: set[str] = set()

        candidate_links: list[str] = []
        candidate_links.extend(self.DOWNLOAD_LINK_PATTERN.findall(content))
        candidate_links.extend(self.GDEMS_LINK_PATTERN.findall(content))
        candidate_links.extend(self.JYSD_LINK_PATTERN.findall(content))
        candidate_links.extend(self.HBFY_PUBLIC_LINK_PATTERN.findall(content))
        candidate_links.extend(self.HBFY_ACCOUNT_LINK_PATTERN.findall(content))
        candidate_links.extend(self.SFDW_LINK_PATTERN.findall(content))
        candidate_links.extend(self.URL_CANDIDATE_PATTERN.findall(content))

        for raw_link in candidate_links:
            link = self._sanitize_link(raw_link)
            if not link or link in seen:
                continue
            if self._is_valid_download_link(link):
                valid_links.append(link)
                seen.add(link)
                logger.info("提取到有效下载链接: %s", link)

        if valid_links:
            logger.info("提取到 %s 个有效下载链接", len(valid_links))
        else:
            logger.info("未找到有效下载链接")

        return valid_links

    def _sanitize_link(self, link: str) -> str:
        """清洗短信中提取的链接，去除尾部标点。"""
        trailing_chars = ".,;:，。；：!！?？)）]】\"'“”"
        return (link or "").strip().rstrip(trailing_chars)

    def _is_valid_download_link(self, link: str) -> bool:
        """
        验证下载链接是否有效（基于结构特征，不强依赖域名）

        Args:
            link: 链接地址

        Returns:
            bool: 是否有效
        """
        link_lower = link.lower()
        parsed = urlparse(link)
        path_lower = parsed.path.lower()
        query_params = parse_qs(parsed.query)

        # 人民法院在线服务网同构链接：hash 路由参数常位于 fragment，直接按关键参数校验
        if "/zxfw/#/pagesajkj/app/wssd/index" in link_lower:
            return all(param in link_lower for param in ["qdbh=", "sdbh=", "sdsin="])

        # 广东电子送达同构链接
        if "/v3/dzsd/" in path_lower:
            return True

        # 简易送达同构链接
        if path_lower.endswith("/sd") and "key" in query_params:
            return True

        # 湖北电子送达同构链接
        if path_lower.endswith("/hb/msg") and "msg" in query_params:
            return True
        if path_lower.endswith("/sfsddz"):
            return True

        # 司法送达网同构链接
        if "/sfsdw//r/" in path_lower:
            return True

        return False

    def extract_verification_code(self, content: str) -> str:
        """
        提取司法送达网验证码

        格式固定：验证码：xxxx

        Args:
            content: 短信内容

        Returns:
            str: 验证码，未找到返回空字符串
        """
        match = self.SFDW_VERIFICATION_CODE_PATTERN.search(content)
        if match:
            code = match.group(1)
            logger.info(f"提取到司法送达网验证码: {code}")
            return code
        return ""

    def extract_case_numbers(self, content: str) -> list[str]:
        """
        提取案号

        Args:
            content: 短信内容

        Returns:
            List[str]: 案号列表
        """
        # 复用 TextUtils 的案号提取功能
        extracted = TextUtils.extract_case_numbers(content)
        case_numbers = extracted

        if case_numbers:
            logger.info(f"提取到案号: {case_numbers}")

        return case_numbers

    def extract_party_names(self, content: str) -> list[str]:
        """
        提取当事人名称

        优先在现有客户中精确查找；未命中时回退到候选提取 + 匹配服务。

        Args:
            content: 短信内容

        Returns:
            List[str]: 当事人名称列表
        """
        # 直接在现有客户数据中查找匹配
        existing_parties = self._find_existing_clients_in_sms(content)

        if existing_parties:
            logger.info(f"在短信中找到现有客户: {existing_parties}")
            return existing_parties

        logger.info("在短信中未找到现有客户，尝试候选提取与匹配")

        candidates: list[str] = []
        try:
            extractor = self.party_candidate_extractor
            if hasattr(extractor, "extract"):
                candidates = list(extractor.extract(content))
        except Exception as exc:
            logger.warning(f"提取当事人候选失败: {exc!s}")
            return []

        if not candidates:
            logger.info("候选当事人为空，返回空列表")
            return []

        try:
            matcher = self.party_matching_service
            if not hasattr(matcher, "extract_and_match_parties_from_sms"):
                logger.warning("当事人匹配服务缺少 extract_and_match_parties_from_sms 接口，返回空列表")
                return []
            matched_clients = matcher.extract_and_match_parties_from_sms(candidates)
        except Exception as exc:
            logger.warning(f"匹配当事人失败: {exc!s}")
            return []

        names: list[str] = []
        seen: set[str] = set()
        for client in matched_clients or []:
            name = str(getattr(client, "name", "")).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)

        if names:
            logger.info(f"通过候选匹配找到当事人: {names}")
            return names

        logger.info("候选匹配未找到当事人，返回空列表")
        return []

    def _find_existing_clients_in_sms(self, content: str) -> list[str]:
        """
        第一步：在现有客户数据中查找在短信内容中出现的客户名称

        Args:
            content: 短信内容

        Returns:
            在短信中找到的现有客户名称列表
        """
        try:
            # 通过客户服务获取所有现有客户
            all_clients = self.client_service.get_all_clients_internal()
            found_parties = []

            logger.info(f"开始在短信中查找现有的 {len(all_clients)} 个客户")

            # 遍历每个客户，检查其名称是否在短信内容中
            for client in all_clients:
                client_name = client.name.strip()

                # 跳过太短的名称（避免误匹配）
                if len(client_name) < 2:
                    continue

                # 检查客户名称是否在短信内容中出现
                if client_name in content:
                    found_parties.append(client_name)
                    logger.info(f"在短信中找到现有客户: {client_name}")

            if found_parties:
                logger.info(f"总共在短信中找到 {len(found_parties)} 个现有客户: {found_parties}")
            else:
                logger.info("在短信中未找到任何现有客户")

            return found_parties

        except Exception as e:
            logger.warning(f"查找现有客户时出错: {e!s}")
            return []

