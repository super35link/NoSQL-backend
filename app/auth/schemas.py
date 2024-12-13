from typing import Optional, Required
from pydantic import BaseModel, EmailStr, Field
from fastapi_users import schemas
from datetime import datetime

class UserRead(schemas.BaseUser[int]):
    """Schema for reading user data"""
    id: int
    email: EmailStr
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserCreate(schemas.BaseUserCreate):
    """Schema for creating a new user"""
    email: EmailStr
    password: str
    username: str = Field(..., min_length=3, max_length=14)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False
    is_verified: Optional[bool] = False

class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating user data"""
    password: Optional[str] = None
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    is_verified: Optional[bool] = None

class TokenSchema(BaseModel):
    """Schema for access token response"""
    access_token: str
    token_type: str = "bearer"

class TokenPayload(BaseModel):
    """Schema for token payload"""
    sub: Optional[int] = None
    exp: Optional[int] = None

class UserResponse(BaseModel):
    """Schema for user response"""
    id: int
    email: str
    username: Optional[str]
    message: str = "Operation successful"

class PasswordReset(BaseModel):
    """Schema for password reset"""
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation"""
    token: str
    new_password: str