"""
用户认证数据模型

定义用户、Token 和认证相关的数据结构
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRole(str, Enum):
    """用户角色"""
    USER = "user"
    ADMIN = "admin"


class UserBase(BaseModel):
    """用户基础模型"""
    email: EmailStr = Field(..., description="邮箱地址")
    name: Optional[str] = Field(None, max_length=100, description="显示名称")


class UserCreate(UserBase):
    """用户注册请求"""
    password: str = Field(..., min_length=8, max_length=128, description="密码")
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """验证密码强度"""
        if len(v) < 8:
            raise ValueError("密码长度至少为 8 个字符")
        
        # 简化验证：只要求长度足够
        # 如需更严格的密码策略，可启用以下检查：
        # has_letter = any(c.isalpha() for c in v)
        # has_digit = any(c.isdigit() for c in v)
        # if not has_letter or not has_digit:
        #     raise ValueError("密码必须包含字母和数字")
        
        return v


class UserLogin(BaseModel):
    """用户登录请求"""
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., description="密码")


class UserResponse(UserBase):
    """用户响应（不含敏感信息）"""
    id: str = Field(..., description="用户 ID")
    role: UserRole = Field(UserRole.USER, description="用户角色")
    is_active: bool = Field(True, description="是否活跃")
    is_verified: bool = Field(False, description="是否已验证邮箱")
    created_at: datetime = Field(..., description="创建时间")
    last_login_at: Optional[datetime] = Field(None, description="最后登录时间")
    
    class Config:
        from_attributes = True


class User(UserBase):
    """用户完整模型（内部使用）"""
    id: str = Field(default_factory=lambda: str(uuid4()), description="用户 ID")
    password_hash: str = Field(..., description="密码哈希")
    role: UserRole = Field(UserRole.USER, description="用户角色")
    
    # 状态
    is_active: bool = Field(True, description="是否活跃")
    is_verified: bool = Field(False, description="是否已验证邮箱")
    
    # 元数据
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    last_login_at: Optional[datetime] = Field(None, description="最后登录时间")
    
    class Config:
        from_attributes = True
    
    def to_response(self) -> UserResponse:
        """转换为响应模型"""
        return UserResponse(
            id=self.id,
            email=self.email,
            name=self.name,
            role=self.role,
            is_active=self.is_active,
            is_verified=self.is_verified,
            created_at=self.created_at,
            last_login_at=self.last_login_at,
        )


class TokenPayload(BaseModel):
    """JWT Token 负载"""
    sub: str = Field(..., description="用户 ID (subject)")
    email: str = Field(..., description="用户邮箱")
    role: str = Field("user", description="用户角色")
    exp: int = Field(..., description="过期时间戳")
    iat: int = Field(..., description="签发时间戳")
    jti: str = Field(default_factory=lambda: str(uuid4()), description="Token ID")
    type: str = Field("access", description="Token 类型: access/refresh")


class TokenPair(BaseModel):
    """Token 对"""
    access_token: str = Field(..., description="Access Token")
    refresh_token: str = Field(..., description="Refresh Token")
    token_type: str = Field("bearer", description="Token 类型")
    expires_in: int = Field(..., description="Access Token 过期时间（秒）")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str = Field(..., description="Access Token")
    token_type: str = Field("bearer", description="Token 类型")
    expires_in: int = Field(..., description="过期时间（秒）")
    user: UserResponse = Field(..., description="用户信息")


class RegisterResponse(BaseModel):
    """注册响应"""
    access_token: str = Field(..., description="Access Token")
    token_type: str = Field("bearer", description="Token 类型")
    expires_in: int = Field(..., description="过期时间（秒）")
    user: UserResponse = Field(..., description="用户信息")


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求（用于从请求体获取）"""
    refresh_token: Optional[str] = Field(None, description="Refresh Token（可选，也可从 Cookie 获取）")


class RefreshTokenResponse(BaseModel):
    """刷新 Token 响应"""
    access_token: str = Field(..., description="新的 Access Token")
    token_type: str = Field("bearer", description="Token 类型")
    expires_in: int = Field(..., description="过期时间（秒）")


class RefreshToken(BaseModel):
    """Refresh Token 存储模型"""
    id: str = Field(default_factory=lambda: str(uuid4()), description="记录 ID")
    user_id: str = Field(..., description="用户 ID")
    token_hash: str = Field(..., description="Token 哈希")
    
    # 元数据
    device_info: Optional[str] = Field(None, description="设备信息")
    ip_address: Optional[str] = Field(None, description="IP 地址")
    user_agent: Optional[str] = Field(None, description="User Agent")
    
    # 状态
    is_revoked: bool = Field(False, description="是否已撤销")
    revoked_at: Optional[datetime] = Field(None, description="撤销时间")
    revoked_reason: Optional[str] = Field(None, description="撤销原因")
    
    # 时间
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    expires_at: datetime = Field(..., description="过期时间")
    last_used_at: Optional[datetime] = Field(None, description="最后使用时间")
    
    class Config:
        from_attributes = True


class LoginLog(BaseModel):
    """登录日志"""
    id: str = Field(default_factory=lambda: str(uuid4()), description="记录 ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    email: str = Field(..., description="登录邮箱")
    
    # 结果
    success: bool = Field(..., description="是否成功")
    failure_reason: Optional[str] = Field(None, description="失败原因")
    
    # 请求信息
    ip_address: Optional[str] = Field(None, description="IP 地址")
    user_agent: Optional[str] = Field(None, description="User Agent")
    
    # 时间
    created_at: datetime = Field(default_factory=datetime.utcnow, description="记录时间")
