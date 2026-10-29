from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password with minimum 8 characters")
    full_name: Optional[str] = Field(None, max_length=100)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserBriefResponse"

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class TokenPayload(BaseModel):
    sub: str  # user id as string
    email: str
    role: str
    type: str  # "access" or "refresh"
    token_version: int = 1
    exp: int

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=16)
    new_password: str = Field(..., min_length=8)

class UserBriefResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool

TokenResponse.model_rebuild()
