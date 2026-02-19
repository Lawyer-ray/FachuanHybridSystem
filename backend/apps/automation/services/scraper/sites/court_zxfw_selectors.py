"""Business logic services."""


class CourtZxfwSelectors:
    PASSWORD_LOGIN_TAB_XPATH = (
        "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
        "/uni-view[1]/uni-view[2]/uni-view[2]"
    )
    ACCOUNT_INPUT_XPATH = (
        "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
        "/uni-view[1]/uni-view[3]/uni-view[1]/uni-view/uni-view"
        "/uni-input/div/input"
    )
    PASSWORD_INPUT_XPATH = (
        "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
        "/uni-view[1]/uni-view[3]/uni-view[2]/uni-view/uni-view"
        "/uni-input/div/input"
    )
    CAPTCHA_INPUT_XPATH = (
        "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
        "/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[1]/uni-view"
        "/uni-input/div/input"
    )
    CAPTCHA_IMAGE_XPATH = (
        "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
        "/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[2]/uni-image/img"
    )
    LOGIN_BUTTON_XPATH = (
        "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
        "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
        "/uni-view[1]/uni-view[4]"
    )
