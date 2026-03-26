"""
认证 API 路由

提供用户注册、登录、Token 刷新等 API 端点
"""

import os
from typing import Annotated, Optional

import asyncpg
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from .dependencies import (
    CurrentActiveUser,
    CurrentUser,
    get_refresh_token_from_cookie,
)
from .models import (
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from .service import (
    AuthService,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# 全局数据库连接池（需要在应用启动时设置）
_db_pool: Optional[asyncpg.Pool] = None


def set_db_pool(pool: asyncpg.Pool) -> None:
    """设置数据库连接池"""
    global _db_pool
    _db_pool = pool


async def get_auth_service() -> AuthService:
    """获取认证服务实例"""
    if _db_pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )
    return AuthService(_db_pool)


def get_client_ip(request: Request) -> Optional[str]:
    """获取客户端 IP"""
    # 优先从 X-Forwarded-For 获取（通过代理时）
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    # 从 X-Real-IP 获取
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # 直接连接的客户端
    if request.client:
        return request.client.host
    
    return None


def get_user_agent(request: Request) -> Optional[str]:
    """获取 User Agent"""
    return request.headers.get("User-Agent")


def set_refresh_token_cookie(
    response: Response,
    refresh_token: str,
    max_age: int = 7 * 24 * 60 * 60,  # 7 天
) -> None:
    """设置 Refresh Token Cookie"""
    secure = os.getenv("DV_AGENT_ENVIRONMENT", "development") == "production"
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/auth",  # 仅在 /auth 路径下发送
    )


def clear_refresh_token_cookie(response: Response) -> None:
    """清除 Refresh Token Cookie"""
    response.delete_cookie(
        key="refresh_token",
        path="/auth",
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
    description="创建新用户账户，返回 Access Token 和用户信息",
)
async def register(
    user_create: UserCreate,
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    用户注册
    
    - **email**: 有效的邮箱地址，必须唯一
    - **password**: 密码，至少 8 个字符，包含字母和数字
    - **name**: 可选的显示名称
    
    成功后返回 Access Token 和 Refresh Token（通过 HttpOnly Cookie）
    """
    try:
        result = await auth_service.register(
            user_create,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
        
        # 设置 Refresh Token Cookie
        # 注册时也需要设置（一步完成注册和登录）
        # 注意：register 方法内部已经创建了 refresh token
        # 但目前的实现没有返回 refresh_token，需要修改
        
        return result
        
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="用户登录",
    description="使用邮箱和密码登录，返回 Access Token",
)
async def login(
    credentials: UserLogin,
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    用户登录
    
    - **email**: 注册的邮箱地址
    - **password**: 用户密码
    
    成功后返回：
    - Access Token（响应体中）
    - Refresh Token（HttpOnly Cookie）
    - 用户基本信息
    """
    try:
        login_response, refresh_token = await auth_service.login(
            email=credentials.email,
            password=credentials.password,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
        
        # 设置 Refresh Token Cookie
        set_refresh_token_cookie(response, refresh_token)
        
        return login_response
        
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    summary="刷新 Token",
    description="使用 Refresh Token 获取新的 Access Token",
)
async def refresh_token(
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    body: Optional[RefreshTokenRequest] = None,
    refresh_token_cookie: Annotated[Optional[str], Depends(get_refresh_token_from_cookie)] = None,
):
    """
    刷新 Access Token
    
    Refresh Token 可以通过以下方式提供：
    1. Cookie（推荐）
    2. 请求体中的 refresh_token 字段
    
    返回新的 Access Token
    """
    # 优先使用 Cookie 中的 Token
    refresh_token = refresh_token_cookie
    
    # 如果 Cookie 中没有，尝试从请求体获取
    if not refresh_token and body and body.refresh_token:
        refresh_token = body.refresh_token
    
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is required",
        )
    
    try:
        result = await auth_service.refresh_access_token(refresh_token)
        return result
        
    except InvalidTokenError as e:
        # 清除无效的 Cookie
        clear_refresh_token_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.message),
        )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="用户登出",
    description="撤销 Refresh Token，清除 Cookie",
)
async def logout(
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    current_user: CurrentUser,
    refresh_token_cookie: Annotated[Optional[str], Depends(get_refresh_token_from_cookie)] = None,
    logout_all: bool = False,
):
    """
    用户登出
    
    - 撤销当前设备的 Refresh Token
    - 清除 Refresh Token Cookie
    
    可选参数：
    - **logout_all**: 如果为 True，撤销用户所有设备的 Token
    """
    await auth_service.logout(
        refresh_token=refresh_token_cookie,
        user_id=current_user.id if logout_all else None,
        logout_all=logout_all,
    )
    
    # 清除 Cookie
    clear_refresh_token_cookie(response)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="获取当前用户信息",
    description="获取当前登录用户的详细信息",
)
async def get_current_user_info(
    current_user: CurrentActiveUser,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    获取当前用户信息
    
    需要有效的 Access Token（Authorization: Bearer <token>）
    
    返回用户的详细信息（不包含敏感信息如密码哈希）
    """
    # 从数据库获取完整用户信息
    user = await auth_service.get_user_by_id(current_user.id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user.to_response()
