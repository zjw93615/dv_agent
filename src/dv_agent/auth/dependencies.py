"""
认证依赖项

提供 FastAPI 依赖注入的认证功能
"""

from typing import Annotated, Optional

from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt import jwt_manager
from .models import TokenPayload, User, UserResponse

# HTTP Bearer 认证方案
security = HTTPBearer(auto_error=False)


async def get_token_from_header(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials],
        Depends(security)
    ] = None,
    authorization: Annotated[Optional[str], Header()] = None,
) -> Optional[str]:
    """
    从请求头获取 Token
    
    支持两种方式：
    1. Authorization: Bearer <token>
    2. 直接的 Authorization header
    """
    if credentials:
        return credentials.credentials
    
    if authorization:
        if authorization.startswith("Bearer "):
            return authorization[7:]
        return authorization
    
    return None


async def get_refresh_token_from_cookie(
    refresh_token: Annotated[Optional[str], Cookie()] = None,
) -> Optional[str]:
    """从 Cookie 获取 Refresh Token"""
    return refresh_token


async def get_current_user_optional(
    token: Annotated[Optional[str], Depends(get_token_from_header)],
) -> Optional[User]:
    """
    获取当前用户（可选）
    
    如果没有 Token 或 Token 无效，返回 None
    """
    if not token:
        return None
    
    payload = jwt_manager.verify_token(token, expected_type="access")
    if not payload:
        return None
    
    # 返回基础用户信息（不查询数据库）
    # 完整信息需要通过 AuthService 获取
    return User(
        id=payload.sub,
        email=payload.email,
        password_hash="",  # 不需要密码
        role=payload.role,
    )


async def get_current_user(
    token: Annotated[Optional[str], Depends(get_token_from_header)],
) -> User:
    """
    获取当前用户（必须）
    
    如果没有 Token 或 Token 无效，抛出 401 错误
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = jwt_manager.verify_token(token, expected_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return User(
        id=payload.sub,
        email=payload.email,
        password_hash="",
        role=payload.role,
    )


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    获取当前活跃用户
    
    检查用户是否激活
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    return current_user


async def get_token_payload(
    token: Annotated[Optional[str], Depends(get_token_from_header)],
) -> TokenPayload:
    """
    获取 Token 负载
    
    用于需要访问完整 Token 信息的场景
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = jwt_manager.verify_token(token, expected_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return payload


def require_role(*roles: str):
    """
    要求特定角色的依赖装饰器
    
    Usage:
        @router.get("/admin")
        async def admin_only(user: Annotated[User, Depends(require_role("admin"))]):
            ...
    """
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    
    return role_checker


# 类型别名，方便使用
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
OptionalUser = Annotated[Optional[User], Depends(get_current_user_optional)]
