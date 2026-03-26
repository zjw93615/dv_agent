"""
认证服务

提供用户注册、登录、Token 管理等核心认证功能
"""

import logging
from datetime import datetime
from typing import Optional

import asyncpg

from .jwt import JWTManager, jwt_manager
from .models import (
    LoginResponse,
    RefreshTokenResponse,
    RegisterResponse,
    TokenPair,
    User,
    UserCreate,
    UserResponse,
)
from .repository import LoginLogRepository, RefreshTokenRepository, UserRepository
from .security import password_hasher

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """认证错误基类"""
    
    def __init__(self, message: str, code: str = "auth_error"):
        self.message = message
        self.code = code
        super().__init__(message)


class InvalidCredentialsError(AuthError):
    """凭据无效"""
    
    def __init__(self):
        super().__init__("Invalid credentials", "invalid_credentials")


class EmailAlreadyExistsError(AuthError):
    """邮箱已存在"""
    
    def __init__(self):
        super().__init__("Email already registered", "email_exists")


class InvalidTokenError(AuthError):
    """Token 无效"""
    
    def __init__(self, message: str = "Invalid token"):
        super().__init__(message, "invalid_token")


class UserNotFoundError(AuthError):
    """用户不存在"""
    
    def __init__(self):
        super().__init__("User not found", "user_not_found")


class UserInactiveError(AuthError):
    """用户未激活"""
    
    def __init__(self):
        super().__init__("User account is inactive", "user_inactive")


class AuthService:
    """认证服务"""
    
    def __init__(
        self,
        pool: asyncpg.Pool,
        jwt: Optional[JWTManager] = None,
    ):
        """
        初始化认证服务
        
        Args:
            pool: PostgreSQL 连接池
            jwt: JWT 管理器，默认使用全局实例
        """
        self._pool = pool
        self._jwt = jwt or jwt_manager
        self._users = UserRepository(pool)
        self._tokens = RefreshTokenRepository(pool)
        self._logs = LoginLogRepository(pool)
    
    async def register(
        self,
        user_create: UserCreate,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> RegisterResponse:
        """
        用户注册
        
        Args:
            user_create: 用户创建请求
            ip_address: 客户端 IP
            user_agent: 客户端 User Agent
            
        Returns:
            注册响应（包含 Token 和用户信息）
            
        Raises:
            EmailAlreadyExistsError: 邮箱已存在
        """
        try:
            # 创建用户
            user = await self._users.create(user_create)
            
            # 生成 Token
            access_token = self._jwt.create_access_token(user)
            refresh_token, expires_at = self._jwt.create_refresh_token(user)
            
            # 存储 Refresh Token
            await self._tokens.create(
                user_id=user.id,
                token=refresh_token,
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            
            logger.info(f"User registered: {user.email}")
            
            return RegisterResponse(
                access_token=access_token,
                token_type="bearer",
                expires_in=self._jwt.access_token_expire_seconds,
                user=user.to_response(),
            )
            
        except ValueError as e:
            if "already registered" in str(e):
                raise EmailAlreadyExistsError()
            raise
    
    async def login(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[LoginResponse, str]:
        """
        用户登录
        
        Args:
            email: 用户邮箱
            password: 用户密码
            ip_address: 客户端 IP
            user_agent: 客户端 User Agent
            
        Returns:
            (登录响应, Refresh Token) - Refresh Token 用于设置 Cookie
            
        Raises:
            InvalidCredentialsError: 凭据无效
        """
        # 验证凭据
        user = await self._users.verify_credentials(email, password)
        
        if not user:
            # 记录失败登录
            await self._logs.create(
                email=email,
                success=False,
                failure_reason="invalid_credentials",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise InvalidCredentialsError()
        
        # 更新最后登录时间
        await self._users.update_last_login(user.id)
        
        # 生成 Token
        access_token = self._jwt.create_access_token(user)
        refresh_token, expires_at = self._jwt.create_refresh_token(user)
        
        # 存储 Refresh Token
        await self._tokens.create(
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        # 记录成功登录
        await self._logs.create(
            email=email,
            success=True,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        logger.info(f"User logged in: {user.email}")
        
        response = LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=self._jwt.access_token_expire_seconds,
            user=user.to_response(),
        )
        
        return response, refresh_token
    
    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> RefreshTokenResponse:
        """
        刷新 Access Token
        
        Args:
            refresh_token: Refresh Token
            
        Returns:
            新的 Access Token 响应
            
        Raises:
            InvalidTokenError: Token 无效或过期
        """
        # 验证 Token 格式
        payload = self._jwt.verify_token(refresh_token, expected_type="refresh")
        if not payload:
            raise InvalidTokenError("Invalid or expired refresh token")
        
        # 检查 Token 是否在数据库中有效
        is_valid = await self._tokens.is_valid(refresh_token)
        if not is_valid:
            raise InvalidTokenError("Refresh token has been revoked")
        
        # 获取用户
        user = await self._users.get_by_id(payload.sub)
        if not user:
            raise InvalidTokenError("User not found")
        
        if not user.is_active:
            raise InvalidTokenError("User account is inactive")
        
        # 更新 Token 最后使用时间
        token_record = await self._tokens.get_by_token(refresh_token)
        if token_record:
            await self._tokens.update_last_used(token_record.id)
        
        # 生成新的 Access Token
        access_token = self._jwt.create_access_token(user)
        
        return RefreshTokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=self._jwt.access_token_expire_seconds,
        )
    
    async def logout(
        self,
        refresh_token: Optional[str] = None,
        user_id: Optional[str] = None,
        logout_all: bool = False,
    ) -> None:
        """
        用户登出
        
        Args:
            refresh_token: 要撤销的 Refresh Token
            user_id: 用户 ID（用于登出所有设备）
            logout_all: 是否登出所有设备
        """
        if logout_all and user_id:
            # 撤销用户所有 Token
            count = await self._tokens.revoke_all_for_user(user_id, "logout_all")
            logger.info(f"Revoked {count} tokens for user {user_id}")
        elif refresh_token:
            # 撤销单个 Token
            await self._tokens.revoke_by_token(refresh_token, "user_logout")
    
    async def get_current_user(self, access_token: str) -> User:
        """
        获取当前用户
        
        Args:
            access_token: Access Token
            
        Returns:
            用户对象
            
        Raises:
            InvalidTokenError: Token 无效
            UserNotFoundError: 用户不存在
            UserInactiveError: 用户未激活
        """
        # 验证 Token
        payload = self._jwt.verify_token(access_token, expected_type="access")
        if not payload:
            raise InvalidTokenError()
        
        # 获取用户
        user = await self._users.get_by_id(payload.sub)
        if not user:
            raise UserNotFoundError()
        
        if not user.is_active:
            raise UserInactiveError()
        
        return user
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        根据 ID 获取用户
        
        Args:
            user_id: 用户 ID
            
        Returns:
            用户对象，不存在返回 None
        """
        return await self._users.get_by_id(user_id)
    
    async def verify_access_token(self, token: str) -> Optional[User]:
        """
        验证 Access Token 并返回用户
        
        Args:
            token: Access Token
            
        Returns:
            用户对象，验证失败返回 None
        """
        try:
            return await self.get_current_user(token)
        except AuthError:
            return None
