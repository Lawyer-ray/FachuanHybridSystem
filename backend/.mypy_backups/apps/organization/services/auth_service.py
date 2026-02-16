"""
认证服务模块
封装用户认证相关的业务逻辑
"""
from django.contrib.auth import authenticate, login, logout
from apps.core.exceptions import AuthenticationError
from ..models import Lawyer


class AuthService:
    """
    认证服务 - 封装认证相关业务逻辑
    
    职责：
    - 用户登录认证
    - 用户登出
    - 认证失败时抛出 AuthenticationError
    """
    
    def login(self, request, username: str, password: str) -> Lawyer:
        """
        用户登录
        
        Args:
            request: Django 请求对象
            username: 用户名
            password: 密码
            
        Returns:
            Lawyer: 认证成功的用户对象
            
        Raises:
            AuthenticationError: 认证失败时抛出
        """
        user = authenticate(request, username=username, password=password)
        if not user:
            raise AuthenticationError(
                message="用户名或密码错误",
                code="INVALID_CREDENTIALS"
            )
        login(request, user)
        return user
    
    def logout(self, request) -> None:
        """
        用户登出
        
        Args:
            request: Django 请求对象
        """
        logout(request)
