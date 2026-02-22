import pytest

from apps.automation.services.scraper.sites.court_zxfw_login_flow import check_login_success


class _StubFirst:
    def __init__(self, *, visible: bool, text: str = ""):
        self._visible = visible
        self._text = text

    def is_visible(self) -> bool:
        return self._visible

    def inner_text(self) -> str:
        return self._text


class _StubLocator:
    def __init__(self, *, count: int, visible: bool = False, text: str = ""):
        self._count = count
        self.first = _StubFirst(visible=visible, text=text)

    def count(self) -> int:
        return self._count


class _StubPage:
    def __init__(self, *, url: str, locators: dict[str, _StubLocator]):
        self.url = url
        self._locators = locators

    def locator(self, selector: str) -> _StubLocator:
        return self._locators.get(selector, _StubLocator(count=0))


@pytest.mark.unit
def test_check_login_success_url_changed():
    page = _StubPage(url="https://zxfw.court.gov.cn/zxfw/#/home", locators={})
    assert check_login_success(page) is True


@pytest.mark.unit
def test_check_login_success_error_visible():
    page = _StubPage(
        url="https://zxfw.court.gov.cn/zxfw/#/pagesGrxx/pc/login/index",
        locators={"text=验证码错误": _StubLocator(count=1, visible=True, text="验证码错误")},
    )
    assert check_login_success(page) is False
