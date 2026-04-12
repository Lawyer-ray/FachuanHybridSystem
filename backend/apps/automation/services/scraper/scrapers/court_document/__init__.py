"""
法院文书下载爬虫模块

支持多种法院文书下载源:
- zxfw.court.gov.cn (人民法院在线服务网)
- sd.gdems.com (睿法智达)
- dzsd.hbfy.gov.cn (湖北电子送达)
- sfpt.cdfy12368.gov.cn (司法送达网)
"""

from .base_court_scraper import BaseCourtDocumentScraper
from .gdems_scraper import GdemsCourtScraper
from .hbfy_scraper import HbfyCourtScraper
from .main import CourtDocumentScraper
from .sfdw_scraper import SfdwCourtScraper
from .zxfw_scraper import ZxfwCourtScraper

__all__ = [
    "BaseCourtDocumentScraper",
    "ZxfwCourtScraper",
    "GdemsCourtScraper",
    "HbfyCourtScraper",
    "SfdwCourtScraper",
    "CourtDocumentScraper",
]
