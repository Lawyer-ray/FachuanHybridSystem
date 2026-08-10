"""案件处理工作流 - HTTP 客户端(httpx 封装)。

与后端 `httpx[http2]==0.28.1` 依赖保持一致,不使用 requests。

认证方式(按优先级):
1. JWT Token(通过 `token` 参数或 `FACHUAN_API_TOKEN` 环境变量)
2. Session 登录(通过 `username`/`password` 参数或 `FACHUAN_USERNAME`/`FACHUAN_PASSWORD` 环境变量)
3. 本地 config.py(不入库,含默认账号)
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = os.environ.get('FACHUAN_BASE_URL', 'http://127.0.0.1:8002')
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_POLL_TIMEOUT = 600.0
_DEFAULT_TIMEOUT = 30.0
_LOGIN_TIMEOUT = 10.0
_UPLOAD_TIMEOUT = 60.0

# 尝试加载本地配置(config.py,不入库,含默认账号)
# 优先级:CLI 参数 > 环境变量 > config.py
try:
    # 相对 _shared/ 的上一级目录(工作流根目录)读取 config.py
    _CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config.py'
    if _CONFIG_PATH.exists():
        import importlib.util as _ilu

        _spec = _ilu.spec_from_file_location('_case_workflow_config', _CONFIG_PATH)
        _local_config = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        if _spec and _spec.loader:
            _spec.loader.exec_module(_local_config)
        else:
            _local_config = None  # type: ignore[assignment]
    else:
        _local_config = None
except Exception:  # pragma: no cover - 配置加载失败不应阻塞
    _local_config = None


class APIClient:
    """后端 API 客户端

    封装 httpx.Client,统一处理认证(JWT/Session)和 CSRF。

    Args:
        base_url: 后端服务地址,默认读 `FACHUAN_BASE_URL` 环境变量
        token: JWT Token,优先级高于 username/password
        username: 登录用户名
        password: 登录密码
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=True,
        )
        self._token = token

        if token:
            self._client.headers['Authorization'] = f'Bearer {token}'

        if username and password:
            self.login(username, password)

    def login(self, username: str, password: str) -> None:
        """通过 Django Admin 登录获取 Session

        Raises:
            PermissionError: 登录失败(凭证错误或网络问题)
        """
        login_path = '/admin/login/'
        try:
            r = self._client.get(login_path, timeout=_LOGIN_TIMEOUT)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise PermissionError(f'无法连接登录页 {login_path}: {e}') from e

        csrf = self._client.cookies.get('csrftoken', '')
        data = {
            'username': username,
            'password': password,
            'csrfmiddlewaretoken': csrf,
            'next': '/admin/',
        }
        headers = {'Referer': f'{self.base_url}{login_path}'}
        try:
            r = self._client.post(
                login_path, data=data, headers=headers, timeout=_LOGIN_TIMEOUT
            )
        except httpx.HTTPError as e:
            raise PermissionError(f'登录请求失败: {e}') from e

        if r.status_code >= 400:
            raise PermissionError(f'登录失败: HTTP {r.status_code}')

        # 登录失败时 Django 会重新渲染登录表单
        if 'id_password' in r.text or '请输入正确的用户名和密码' in r.text:
            raise PermissionError('登录失败: 用户名或密码错误')

        logger.info('已登录后端: %s', username)

    def get(self, path: str, **kwargs) -> dict:
        """发送 GET 请求,返回 JSON"""
        r = self._client.get(path, **kwargs)
        return self._handle(r)

    def post_multipart(
        self,
        path: str,
        fields: dict,
        file_path: Path,
        file_field: str = 'file',
    ) -> dict:
        """发送 multipart/form-data 请求(用于文件上传)

        Args:
            path: API 路径(以 / 开头)
            fields: 普通表单字段
            file_path: 要上传的文件路径
            file_field: 文件字段名,默认 'file'
        """
        file_path = Path(file_path)
        with open(file_path, 'rb') as f:
            files = {file_field: (file_path.name, f, 'application/octet-stream')}
            headers = {}
            csrf = self._client.cookies.get('csrftoken', '')
            if csrf:
                headers['X-CSRFToken'] = csrf
            r = self._client.post(
                path, data=fields, files=files, headers=headers, timeout=_UPLOAD_TIMEOUT
            )
        return self._handle(r)

    def close(self) -> None:
        """关闭底层 HTTP 连接"""
        self._client.close()

    def __enter__(self) -> APIClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _handle(r: httpx.Response) -> dict:
        if r.status_code >= 400:
            raise RuntimeError(f'API 调用失败: HTTP {r.status_code} - {r.text[:500]}')
        return r.json()


class DocumentParsingClient:
    """文档解析 API 客户端

    封装 `/api/v1/document-parsing/` 接口,自动处理同步/异步轮询。

    Args:
        api_client: APIClient 实例
        poll_interval: 异步任务轮询间隔(秒)
        poll_timeout: 异步任务最大等待时间(秒)
    """

    PARSE_PATH = '/api/v1/document-parsing/parse'
    TASK_PATH = '/api/v1/document-parsing/task/{task_id}'

    def __init__(
        self,
        api_client: APIClient,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
    ) -> None:
        self.api = api_client
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    def parse(
        self,
        file_path: str | Path,
        backend: str = 'auto',
        return_markdown: bool = True,
        extract_tables: bool = True,
        extract_images: bool = False,
    ) -> dict:
        """解析文档,自动处理同步/异步

        Returns:
            统一结构的 dict,包含字段:
            - success: bool
            - status: 'completed' / 'failed' / 'timeout'
            - task_id: str | None
            - text: str | None(纯文本)
            - markdown: str | None(Markdown 格式)
            - metadata: dict | None
            - parse_method: str | None
            - error: str | None
        """
        fields = {
            'backend': backend,
            'return_markdown': 'true' if return_markdown else 'false',
            'extract_tables': 'true' if extract_tables else 'false',
            'extract_images': 'true' if extract_images else 'false',
        }
        resp = self.api.post_multipart(self.PARSE_PATH, fields, Path(file_path))
        return self._normalize(resp)

    def _normalize(self, resp: dict) -> dict:
        if not resp.get('success'):
            return self._failed(resp.get('error', '未知错误'))

        # 同步模式:直接返回
        if resp.get('status') == 'completed':
            return {
                'success': True,
                'status': 'completed',
                'task_id': None,
                'text': resp.get('text'),
                'markdown': resp.get('markdown'),
                'metadata': resp.get('metadata'),
                'parse_method': resp.get('parse_method'),
                'error': None,
            }

        # 异步模式:轮询
        task_id = resp.get('task_id')
        if not task_id:
            return self._failed('响应缺少 task_id')
        return self._poll_task(task_id)

    def _poll_task(self, task_id: str) -> dict:
        path = self.TASK_PATH.format(task_id=task_id)
        start = time.time()
        last_status: str | None = None

        while time.time() - start < self.poll_timeout:
            resp = self.api.get(path)
            status = resp.get('status')
            if status != last_status:
                logger.info('解析任务 %s 状态: %s', task_id[:8], status)
                last_status = status

            if status == 'success':
                r = resp.get('result') or {}
                return {
                    'success': True,
                    'status': 'completed',
                    'task_id': task_id,
                    'text': r.get('text'),
                    'markdown': r.get('markdown'),
                    'metadata': r.get('metadata'),
                    'parse_method': r.get('parse_method'),
                    'error': None,
                }
            if status in ('failure', 'failed'):
                r = resp.get('result') or {}
                return self._failed(
                    r.get('error', '解析任务失败'), task_id=task_id
                )
            time.sleep(self.poll_interval)

        return self._failed(
            f'任务等待超时({self.poll_timeout}s)', task_id=task_id, status='timeout'
        )

    @staticmethod
    def _failed(
        error: str, task_id: str | None = None, status: str = 'failed'
    ) -> dict:
        return {
            'success': False,
            'status': status,
            'task_id': task_id,
            'text': None,
            'markdown': None,
            'metadata': None,
            'parse_method': None,
            'error': error,
        }


def _cfg(name: str) -> str | None:
    """从本地 config.py 读取配置项"""
    return getattr(_local_config, name, None) if _local_config else None


def build_api_client(
    base_url: str | None = None,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> APIClient:
    """根据参数、环境变量和本地 config.py 构建 API 客户端

    优先级(高 → 低):
    1. 显式传入的参数
    2. 环境变量 `FACHUAN_API_TOKEN` / `FACHUAN_USERNAME` + `FACHUAN_PASSWORD` / `FACHUAN_BASE_URL`
    3. 本地 `config.py`(不入库,含默认账号)

    Raises:
        ValueError: 未提供有效认证信息
    """
    base_url = (
        base_url
        or os.environ.get('FACHUAN_BASE_URL')
        or _cfg('BASE_URL')
        or DEFAULT_BASE_URL
    )
    token = token or os.environ.get('FACHUAN_API_TOKEN') or _cfg('TOKEN')
    username = username or os.environ.get('FACHUAN_USERNAME') or _cfg('USERNAME')
    password = password or os.environ.get('FACHUAN_PASSWORD') or _cfg('PASSWORD')

    if token:
        return APIClient(base_url=base_url, token=token)
    if username and password:
        return APIClient(base_url=base_url, username=username, password=password)

    raise ValueError(
        '未提供有效认证信息。请通过以下方式之一配置:\n'
        '  1. CLI 参数 --token 或 --username/--password\n'
        '  2. 环境变量 FACHUAN_API_TOKEN 或 FACHUAN_USERNAME + FACHUAN_PASSWORD\n'
        '  3. 复制 config.example.py 为 config.py 并填入账号\n'
        '  - FACHUAN_BASE_URL (默认 http://127.0.0.1:8002)'
    )
