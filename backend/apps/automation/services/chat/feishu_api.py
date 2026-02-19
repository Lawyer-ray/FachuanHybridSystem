"""API endpoints."""

from __future__ import annotations

"""
飞书API通信模块

本模块提供飞书API通信功能,包括:
- Token获取和管理
- 群聊创建和管理
- 消息发送
- 文件上传
- 错误分类和处理

作为 FeishuChatProvider 的 Mixin 使用.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from apps.automation.utils.logging_mixins.common import sanitize_url
from apps.core.exceptions import (
    ChatCreationException,
    ChatProviderException,
    ConfigurationException,
    MessageSendException,
    OwnerSettingException,
    owner_network_error,
    owner_not_found_error,
    owner_permission_error,
    owner_timeout_error,
    owner_validation_error,
)
from apps.core.httpx_clients import get_sync_http_client
from apps.core.path import Path

if TYPE_CHECKING:
    from .base import ChatResult

logger = logging.getLogger(__name__)


class FeishuApiMixin:
    """飞书API通信 Mixin

    提供飞书API通信相关的方法,包括:
    - Token获取和缓存
    - 群聊创建
    - 消息发送
    - 文件上传和发送
    - 群聊信息获取
    - 群主验证和重试
    - 错误分类
    """

    # 飞书API基础URL
    BASE_URL = "https://open.feishu.cn/open-apis"

    # API端点
    ENDPOINTS: ClassVar = {
        "tenant_access_token": "/auth/v3/tenant_access_token/internal",
        "create_chat": "/im/v1/chats",
        "send_message": "/im/v1/messages",
        "upload_file": "/im/v1/files",
        "get_chat": "/im/v1/chats/{chat_id}",
    }

    # Mixin 依赖的宿主属性声明
    config: dict[str, Any]
    _access_token: str | None
    _token_expires_at: datetime | None

    def _get_file_type(self, file_path: str) -> str: ...  # type: ignore[empty-body]
    def _get_mime_type(self, file_path: str) -> str: ...  # type: ignore[empty-body]

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """发送HTTP请求

        Args:
            method: HTTP方法
            url: 请求URL
            params: 查询参数
            json_data: JSON请求体
            headers: 请求头
            files: 文件数据
            data: 表单数据
            timeout: 超时时间

        Returns:
            httpx.Response: HTTP响应
        """
        request_timeout = timeout if timeout is not None else self.config.get("TIMEOUT", 30)
        client = get_sync_http_client()
        return client.request(
            method=method,
            url=url,
            params=params,
            json=json_data,
            headers=headers,
            files=files,
            data=data,
            timeout=request_timeout,
        )

    def _get_tenant_access_token(self) -> Any:
        """获取租户访问令牌

        使用应用ID和密钥获取访问令牌,支持令牌缓存和自动刷新.

        Returns:
            str: 访问令牌

        Raises:
            ConfigurationException: 当配置不完整时
            ChatProviderException: 当API调用失败时
        """
        # 检查缓存的令牌是否有效
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now() < self._token_expires_at - timedelta(minutes=5)
        ):  # 提前5分钟刷新
            return self._access_token

        # 检查必要配置
        app_id = self.config.get("APP_ID")
        app_secret = self.config.get("APP_SECRET")

        if not app_id or not app_secret:
            raise ConfigurationException(
                message="飞书APP_ID或APP_SECRET未配置", platform="feishu", missing_config="APP_ID, APP_SECRET"
            )

        # 请求新的访问令牌
        url = f"{self.BASE_URL}{self.ENDPOINTS['tenant_access_token']}"
        payload: dict[str, Any] = {"app_id": app_id, "app_secret": app_secret}

        try:
            timeout = self.config.get("TIMEOUT", 30)
            response = self._request("POST", url, json_data=payload, timeout=timeout, headers={})
            response.raise_for_status()

            resp_data = response.json()

            # 检查飞书API响应
            if resp_data.get("code") != 0:
                error_msg = resp_data.get("msg", "未知错误")
                raise ChatProviderException(
                    message=f"获取飞书访问令牌失败: {error_msg}",
                    platform="feishu",
                    error_code=str(resp_data.get("code")),
                    errors={},
                )

            # 缓存令牌
            self._access_token = resp_data["tenant_access_token"]
            expires_in = resp_data.get("expire", 7200)  # 默认2小时
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            logger.debug("已获取飞书访问令牌")
            return self._access_token

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error(f"请求飞书访问令牌失败: {e!s}")
            raise ChatProviderException(
                message=f"网络请求失败: {e!s}", platform="feishu", errors={"original_error": str(e)}
            ) from e
        except (KeyError, ValueError) as e:
            logger.error(f"解析飞书API响应失败: {e!s}")
            raise ChatProviderException(
                message=f"API响应格式错误: {e!s}", platform="feishu", errors={"original_error": str(e)}
            ) from e

    def _upload_file(self, file_path: str) -> str:
        """上传文件到飞书并获取file_key

        Args:
            file_path: 文件路径

        Returns:
            str: 飞书文件key

        Raises:
            MessageSendException: 当文件上传失败时
        """
        try:
            # 获取访问令牌
            access_token = self._get_tenant_access_token()

            # 构建请求
            url = f"{self.BASE_URL}{self.ENDPOINTS['upload_file']}"
            req_headers: dict[str, Any] = {"Authorization": f"Bearer {access_token}"}

            file_path_obj = Path(file_path)
            file_name = file_path_obj.name
            file_type = self._get_file_type(file_path)

            with file_path_obj.open("rb") as file:
                upload_files: dict[str, Any] = {"file": (file_name, file, "application/octet-stream")}
                form_data: dict[str, Any] = {"file_type": file_type, "file_name": file_name}

                # 发送请求
                timeout = self.config.get("TIMEOUT", 30)
                response = self._request(
                    "POST",
                    url,
                    headers=req_headers,
                    files=upload_files,
                    data=form_data,
                    timeout=timeout,
                )
                response.raise_for_status()

            resp_data = response.json()

            # 检查飞书API响应
            if resp_data.get("code") != 0:
                error_msg = resp_data.get("msg", "未知错误")
                error_code = str(resp_data.get("code"))

                logger.error(f"上传飞书文件失败: {error_msg} (code: {error_code})")

                raise MessageSendException(
                    message=f"文件上传失败: {error_msg}", platform="feishu", error_code=error_code, errors={}
                )

            # 提取file_key
            file_data = resp_data.get("data", {})
            file_key = file_data.get("file_key")

            if not file_key:
                raise MessageSendException(
                    message="API响应中缺少文件key", platform="feishu", errors={"api_response": resp_data}
                )

            logger.debug(f"成功上传文件到飞书: {file_name} (key: {file_key})")
            return file_key  # type: ignore[no-any-return]

        except MessageSendException:
            raise
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error(f"上传飞书文件网络请求失败: {e!s}")
            raise MessageSendException(message=f"文件上传网络请求失败: {e!s}", platform="feishu", errors={}) from e
        except Exception as e:
            logger.error(f"上传飞书文件时发生未知错误: {e!s}")
            raise MessageSendException(message=f"文件上传时发生未知错误: {e!s}", platform="feishu", errors={}) from e

    def _send_file_message(self, chat_id: str, file_key: str, file_path: str) -> ChatResult:
        """发送文件消息

        根据飞书官方API文档,发送文件消息时 content 中只需要 file_key.
        参考:https://open.feishu.cn/document/server-docs/im-v1/message/create

        Args:
            chat_id: 群聊ID
            file_key: 飞书文件key
            file_path: 原始文件路径(用于日志记录)

        Returns:
            ChatResult: 文件发送结果
        """
        from .base import ChatResult

        try:
            # 获取访问令牌
            access_token = self._get_tenant_access_token()

            # 构建请求URL和查询参数
            url = f"{self.BASE_URL}{self.ENDPOINTS['send_message']}"
            params: dict[str, Any] = {"receive_id_type": "chat_id"}
            req_headers: dict[str, Any] = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8",
            }

            # 根据飞书官方示例,content 中只需要 file_key
            file_name = Path(file_path).name
            content: dict[str, Any] = {"file_key": file_key}

            payload: dict[str, Any] = {"receive_id": chat_id, "msg_type": "file", "content": json.dumps(content)}

            logger.debug(f"发送飞书文件消息请求URL: {sanitize_url(url)}")
            logger.debug(f"发送飞书文件消息查询参数: {params}")
            logger.debug(f"发送飞书文件消息请求体: {payload}")

            # 发送请求
            timeout = self.config.get("TIMEOUT", 30)
            response = self._request(
                "POST",
                url,
                params=params,
                json_data=payload,
                headers=req_headers,
                timeout=timeout,
            )

            logger.debug(f"飞书API响应状态码: {response.status_code}")
            logger.debug(f"飞书API响应内容: {response.text}")

            response.raise_for_status()

            resp_data = response.json()

            # 检查飞书API响应
            if resp_data.get("code") != 0:
                error_msg = resp_data.get("msg", "未知错误")
                error_code = str(resp_data.get("code"))

                logger.error(f"发送飞书文件消息失败: {error_msg} (code: {error_code})")
                logger.error(f"完整响应: {resp_data}")

                raise MessageSendException(
                    message=f"发送文件消息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    chat_id=chat_id,
                    errors={
                        "api_response": resp_data,
                        "file_key": file_key,
                        "file_path": file_path,
                        "request_payload": payload,
                    },
                )

            # 提取消息信息
            message_data = resp_data.get("data", {})
            message_id = message_data.get("message_id")

            logger.info(f"成功发送飞书文件到群聊: {chat_id} (文件: {file_name}, 消息ID: {message_id})")

            return ChatResult(
                success=True, chat_id=chat_id, message=f"文件发送成功: {file_name}", raw_response=resp_data
            )

        except MessageSendException:
            raise
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error(f"发送飞书文件消息网络请求失败: {e!s}")
            raise MessageSendException(
                message=f"发送文件消息网络请求失败: {e!s}", platform="feishu", chat_id=chat_id, errors={}
            ) from e

    def _classify_feishu_error(
        self, error_code: str, error_msg: str
    ) -> OwnerSettingException | type[ChatCreationException]:
        """分类飞书API错误

        根据飞书API返回的错误代码和错误消息,分类为相应的异常类型.

        Args:
            error_code: 飞书API错误代码
            error_msg: 飞书API错误消息

        Returns:
            OwnerSettingException 实例或 ChatCreationException 类
        """
        error_msg_lower = error_msg.lower()

        # 权限相关错误
        if (
            error_code in ["99991663", "99991664", "99991665"]
            or "permission" in error_msg_lower
            or "forbidden" in error_msg_lower
            or "access denied" in error_msg_lower
        ):
            return owner_permission_error()

        # 用户不存在错误
        if (
            error_code in ["99991400", "99991401"]
            or "user not found" in error_msg_lower
            or "invalid user" in error_msg_lower
            or "user does not exist" in error_msg_lower
        ):
            return owner_not_found_error()

        # 参数验证错误
        if (
            error_code in ["99991400", "1400"]
            or "invalid parameter" in error_msg_lower
            or "parameter error" in error_msg_lower
            or "validation failed" in error_msg_lower
        ):
            return owner_validation_error()

        # 超时错误
        if "timeout" in error_msg_lower or "timed out" in error_msg_lower:
            return owner_timeout_error()

        # 网络错误
        if "network" in error_msg_lower or "connection" in error_msg_lower or "request failed" in error_msg_lower:
            return owner_network_error()

        # 默认返回通用群聊创建异常类
        return ChatCreationException

    def _convert_union_id_to_open_id(self, union_id: str) -> str | None:
        """转换union_id为open_id

        通过飞书API将union_id转换为open_id.
        使用用户信息查询API进行转换.

        Args:
            union_id: 飞书用户的union_id

        Returns:
            对应的open_id,如果转换失败则返回None
        """
        try:
            # 获取访问令牌
            access_token = self._get_tenant_access_token()

            # 构建请求URL
            url = f"{self.BASE_URL}/contact/v3/users/{union_id}"
            req_headers: dict[str, Any] = {"Authorization": f"Bearer {access_token}"}

            # 查询参数:指定返回open_id
            params: dict[str, Any] = {"user_id_type": "open_id"}

            # 发送请求
            timeout = self.config.get("TIMEOUT", 30)
            response = self._request("GET", url, params=params, headers=req_headers, timeout=timeout)
            response.raise_for_status()

            resp_data = response.json()

            # 检查API响应
            if resp_data.get("code") == 0:
                user_data = resp_data.get("data", {}).get("user", {})
                open_id = user_data.get("open_id")

                if open_id:
                    logger.info(f"成功转换union_id为open_id: {union_id} -> {open_id}")
                    return open_id  # type: ignore[no-any-return]
                else:
                    logger.warning(f"API响应中缺少open_id: {union_id}")
                    return None
            else:
                error_msg = resp_data.get("msg", "未知错误")
                logger.warning(f"转换union_id失败: {union_id}, 错误: {error_msg}")
                return None

        except Exception as e:
            logger.error(f"转换union_id时发生错误: {union_id}, 错误: {e!s}")
            return None
