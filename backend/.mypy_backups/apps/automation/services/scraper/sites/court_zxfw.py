"""
全国法院"一张网"服务 (zxfw.court.gov.cn)
提供登录、立案、查询等功能
"""
import logging
import time
from typing import Dict, Any, Optional
from playwright.sync_api import Page, BrowserContext
from pathlib import Path
logger = logging.getLogger('apps.automation')

class CourtZxfwService:
    """
    全国法院"一张网"服务 - 支持依赖注入
    
    功能模块化设计：
    - login(): 登录
    - file_case(): 立案
    - query_case(): 查询案件
    - download_document(): 下载文书
    
    依赖注入：
    - captcha_recognizer: 验证码识别器（可选）
    - token_service: Token 服务（可选）
    """
    BASE_URL = 'https://zxfw.court.gov.cn/zxfw'
    LOGIN_URL = f'{BASE_URL}/#/pagesGrxx/pc/login/index'

    def __init__(self, page: Page, context: BrowserContext, captcha_recognizer: Optional['CaptchaRecognizer']=None, token_service: Optional['TokenService']=None, site_name: str='court_zxfw'):
        """
        初始化服务
        
        Args:
            page: Playwright Page 对象
            context: Playwright BrowserContext 对象
            captcha_recognizer: 验证码识别器，None 则使用默认的 DdddocrRecognizer
            token_service: Token 服务，None 则使用默认的 TokenService
            site_name: 网站名称，用于 Token 管理，默认 "court_zxfw"
        """
        self.page = page
        self.context = context
        self.site_name = site_name
        self.is_logged_in = False
        if captcha_recognizer is None:
            from ..core.captcha_recognizer import DdddocrRecognizer
            self.captcha_recognizer = DdddocrRecognizer(show_ad=False)
            logger.info('使用默认的 DdddocrRecognizer')
        else:
            self.captcha_recognizer = captcha_recognizer
            logger.info(f'使用注入的验证码识别器: {type(captcha_recognizer).__name__}')
        self._token_service = token_service
        if token_service is not None:
            logger.info(f'使用注入的 Token 服务: {type(token_service).__name__}')

    @property
    def token_service(self) -> Any:
        """获取 Token 服务（延迟加载）"""
        if self._token_service is None:
            from apps.core.interfaces import ServiceLocator
            self._token_service = ServiceLocator.get_token_service()
            logger.info('使用 ServiceLocator 获取 TokenService')
        return self._token_service

    def login(self, account: str, password: str, max_captcha_retries: int=3, save_debug: bool=False, credential_id: int=None) -> Dict[str, Any]:
        """
        登录全国法院"一张网"
        
        Args:
            account: 账号
            password: 密码
            max_captcha_retries: 验证码识别最大重试次数
            save_debug: 是否保存调试信息
            credential_id: 凭证ID，用于记录Token获取历史
            
        Returns:
            登录结果字典
            
        Raises:
            ValueError: 登录失败
        """
        logger.info('=' * 60)
        logger.info("开始登录全国法院'一张网'...")
        logger.info('=' * 60)
        captured_token = {'value': None}
        try:

            def handle_response(response):
                """监听响应，提取 token"""
                try:
                    url = response.url.lower()
                    if '/api/' in url:
                        logger.info(f'🌐 API 响应: {response.url} (状态: {response.status})')
                    if 'login' in url and response.status == 200:
                        content_type = response.headers.get('content-type', '').lower()
                        logger.info(f'📡 捕获到登录接口响应: {response.url}')
                        logger.info(f'   状态码: {response.status}')
                        logger.info(f'   Content-Type: {content_type}')
                        if not ('application/json' in content_type or 'text/' in content_type):
                            logger.info(f'   跳过非文本响应: {content_type}')
                            return
                        try:
                            response_text = response.text()
                            logger.info(f'📄 响应文本: {response_text[:500]}...')
                            import json
                            response_body = json.loads(response_text)
                            logger.info(f'✅ JSON 解析成功')
                            logger.info(f'📦 响应结构: {list(response_body.keys())}')
                            if isinstance(response_body, dict):
                                if 'data' in response_body and isinstance(response_body['data'], dict):
                                    logger.info(f'🔍 检查 data 字段: {list(response_body['data'].keys())}')
                                    token = response_body['data'].get('token') or response_body['data'].get('access_token') or response_body['data'].get('accessToken')
                                    if token:
                                        captured_token['value'] = token
                                        logger.info(f'✅✅✅ 从 data.token 捕获到 Token: {token[:30]}...')
                                        logger.info(f'   Token 长度: {len(token)} 字符')
                                        return
                                if 'result' in response_body and isinstance(response_body['result'], dict):
                                    logger.info(f'🔍 检查 result 字段: {list(response_body['result'].keys())}')
                                    token = response_body['result'].get('token') or response_body['result'].get('access_token') or response_body['result'].get('accessToken')
                                    if token:
                                        captured_token['value'] = token
                                        logger.info(f'✅✅✅ 从 result.token 捕获到 Token: {token[:30]}...')
                                        logger.info(f'   Token 长度: {len(token)} 字符')
                                        return
                                token = response_body.get('token') or response_body.get('access_token') or response_body.get('accessToken')
                                if token:
                                    captured_token['value'] = token
                                    logger.info(f'✅✅✅ 从根级别捕获到 Token: {token[:30]}...')
                                    logger.info(f'   Token 长度: {len(token)} 字符')
                                    return
                                logger.warning(f'⚠️⚠️⚠️ 未能从响应中提取 Token')
                                logger.warning(f'   响应结构: {list(response_body.keys())}')
                                if 'data' in response_body:
                                    logger.warning(f'   data 字段类型: {type(response_body['data'])}')
                                    if isinstance(response_body['data'], dict):
                                        logger.warning(f'   data 字段内容: {list(response_body['data'].keys())}')
                        except json.JSONDecodeError as e:
                            logger.error(f'❌ JSON 解析失败: {e}')
                            logger.error(f'   响应文本: {response_text[:200]}')
                        except Exception as e:
                            logger.error(f'❌ 解析登录响应失败: {e}', exc_info=True)
                except Exception as e:
                    logger.error(f'❌ 响应监听器处理失败: {e}', exc_info=True)
            self.page.on('response', handle_response)
            logger.info('=' * 80)
            logger.info('✅✅✅ 已设置响应监听器，准备捕获 Token')
            logger.info('=' * 80)
            logger.info(f'导航到登录页: {self.LOGIN_URL}')
            self.page.goto(self.LOGIN_URL, timeout=30000, wait_until='networkidle')
            self._random_wait(2, 3)
            if save_debug:
                self._save_screenshot('01_login_page')
            logger.info("点击'密码登录'")
            password_login_xpath = '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[2]/uni-view[2]'
            try:
                password_tab = self.page.locator(f'xpath={password_login_xpath}')
                password_tab.wait_for(state='visible', timeout=10000)
                password_tab.click()
                self._random_wait(1, 2)
                if save_debug:
                    self._save_screenshot('02_password_tab_clicked')
            except Exception as e:
                logger.warning(f'点击密码登录失败: {e}，可能已经在密码登录页面')
            logger.info(f'输入账号: {account}')
            account_xpath = '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[1]/uni-view/uni-view/uni-input/div/input'
            account_input = self.page.locator(f'xpath={account_xpath}')
            account_input.wait_for(state='visible', timeout=10000)
            account_input.fill(account)
            self._random_wait(0.5, 1)
            logger.info('输入密码')
            password_xpath = '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[2]/uni-view/uni-view/uni-input/div/input'
            password_input = self.page.locator(f'xpath={password_xpath}')
            password_input.wait_for(state='visible', timeout=10000)
            password_input.fill(password)
            self._random_wait(0.5, 1)
            if save_debug:
                self._save_screenshot('03_credentials_filled')
            captcha_success = False
            for attempt in range(1, max_captcha_retries + 1):
                logger.info(f'验证码识别尝试 {attempt}/{max_captcha_retries}')
                try:
                    captcha_text = self._recognize_captcha(save_debug=save_debug)
                    if not captcha_text:
                        logger.warning(f'验证码识别失败（尝试 {attempt}）')
                        if attempt < max_captcha_retries:
                            self._refresh_captcha()
                            continue
                        else:
                            raise ValueError('验证码识别失败，已达最大重试次数')
                    logger.info(f'输入验证码: {captcha_text}')
                    captcha_input_xpath = '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[1]/uni-view/uni-input/div/input'
                    captcha_input = self.page.locator(f'xpath={captcha_input_xpath}')
                    captcha_input.wait_for(state='visible', timeout=10000)
                    captcha_input.fill(captcha_text)
                    self._random_wait(0.5, 1)
                    if save_debug:
                        self._save_screenshot(f'04_captcha_filled_attempt_{attempt}')
                    logger.info('点击登录按钮')
                    login_button_xpath = '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[4]'
                    login_button = self.page.locator(f'xpath={login_button_xpath}')
                    login_button.wait_for(state='visible', timeout=10000)
                    login_button.click()
                    logger.info('等待登录结果...')
                    self._random_wait(3, 5)
                    if save_debug:
                        self._save_screenshot(f'05_after_login_attempt_{attempt}')
                    if self._check_login_success():
                        logger.info('✅ 登录成功！')
                        self.is_logged_in = True
                        captcha_success = True
                        break
                    else:
                        logger.warning(f'登录失败（尝试 {attempt}），可能是验证码错误')
                        if attempt < max_captcha_retries:
                            captcha_input.fill('')
                            self._refresh_captcha()
                            continue
                        else:
                            raise ValueError('登录失败，已达最大重试次数')
                except Exception as e:
                    logger.error(f'登录尝试 {attempt} 出错: {e}')
                    if attempt >= max_captcha_retries:
                        raise
                    self._random_wait(2, 3)
            if not captcha_success:
                raise ValueError('登录失败')
            return {'success': True, 'message': '登录成功', 'url': self.page.url, 'token': captured_token['value']}
        except Exception as e:
            logger.error(f'登录失败: {e}', exc_info=True)
            if save_debug:
                self._save_screenshot('error_login_failed')
            raise ValueError(f'登录失败: {e}')

    def _recognize_captcha(self, save_debug: bool=False) -> Optional[str]:
        """
        识别验证码 - 使用注入的识别器
        
        Args:
            save_debug: 是否保存调试信息
            
        Returns:
            识别的验证码文本，失败返回 None
        """
        try:
            captcha_img_xpath = '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[2]/uni-image/img'
            captcha_img = self.page.locator(f'xpath={captcha_img_xpath}')
            captcha_img.wait_for(state='visible', timeout=10000)
            self._random_wait(0.5, 1)
            if save_debug:
                from django.conf import settings
                captcha_screenshot = captcha_img.screenshot()
                debug_dir = Path(settings.MEDIA_ROOT) / 'automation' / 'debug'
                debug_dir.mkdir(parents=True, exist_ok=True)
                captcha_path = debug_dir / f'captcha_{int(time.time())}.png'
                with open(captcha_path, 'wb') as f:
                    f.write(captcha_screenshot)
                logger.info(f'验证码图片已保存: {captcha_path}')
            captcha_text = self.captcha_recognizer.recognize_from_element(self.page, f'xpath={captcha_img_xpath}')
            if captcha_text:
                logger.info(f'验证码识别结果: {captcha_text}')
            else:
                logger.warning('验证码识别失败')
            return captcha_text
        except Exception as e:
            logger.error(f'获取验证码图片失败: {e}')
            return None

    def _refresh_captcha(self) -> None:
        """刷新验证码（点击验证码图片）"""
        try:
            captcha_img_xpath = '/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[2]/uni-image/img'
            captcha_img = self.page.locator(f'xpath={captcha_img_xpath}')
            captcha_img.click()
            logger.info('已刷新验证码')
            self._random_wait(1, 2)
        except Exception as e:
            logger.warning(f'刷新验证码失败: {e}')

    def _check_login_success(self) -> bool:
        """
        检查是否登录成功
        
        Returns:
            是否登录成功
        """
        try:
            current_url = self.page.url
            logger.info(f'当前 URL: {current_url}')
            if 'login' not in current_url.lower():
                logger.info('URL 已跳转，登录可能成功')
                return True
            try:
                error_selectors = ['text=验证码错误', 'text=账号或密码错误', 'text=登录失败', '.error-message', '.login-error']
                for selector in error_selectors:
                    error_elem = self.page.locator(selector)
                    if error_elem.count() > 0 and error_elem.first.is_visible():
                        error_text = error_elem.first.inner_text()
                        logger.warning(f'发现错误提示: {error_text}')
                        return False
            except:
                pass
            try:
                user_info_selectors = ['text=退出登录', 'text=个人中心', '.user-info', '.user-avatar']
                for selector in user_info_selectors:
                    elem = self.page.locator(selector)
                    if elem.count() > 0:
                        logger.info(f'找到登录后的元素: {selector}')
                        return True
            except:
                pass
            return 'login' not in current_url.lower()
        except Exception as e:
            logger.warning(f'检查登录状态失败: {e}')
            return False

    def _random_wait(self, min_sec: float=0.5, max_sec: float=2.0) -> None:
        """随机等待"""
        import random
        wait_time = random.uniform(min_sec, max_sec)
        time.sleep(wait_time)

    def _save_screenshot(self, name: str) -> str:
        """保存截图"""
        from django.conf import settings
        from datetime import datetime
        screenshot_dir = Path(settings.MEDIA_ROOT) / 'automation' / 'screenshots'
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f'{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png'
        filepath = screenshot_dir / filename
        self.page.screenshot(path=str(filepath))
        logger.info(f'截图已保存: {filepath}')
        return str(filepath)

    def file_case(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        立案
        
        Args:
            case_data: 案件数据
            
        Returns:
            立案结果
        """
        if not self.is_logged_in:
            raise ValueError('请先登录')
        raise NotImplementedError('立案功能待实现')

    def query_case(self, case_number: str) -> Dict[str, Any]:
        """
        查询案件
        
        Args:
            case_number: 案号
            
        Returns:
            案件信息
        """
        if not self.is_logged_in:
            raise ValueError('请先登录')
        raise NotImplementedError('查询功能待实现')

    def download_document(self, document_url: str) -> Dict[str, Any]:
        """
        下载文书
        
        Args:
            document_url: 文书链接
            
        Returns:
            下载结果
        """
        if not self.is_logged_in:
            raise ValueError('请先登录')
        raise NotImplementedError('下载功能待实现')