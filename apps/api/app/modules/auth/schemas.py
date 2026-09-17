from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: str
    branch_id: int | None
    tenant_id: int | None = None
    department: str | None = None
    subgroup: str | None = None
    permissions: list[str] = Field(default_factory=list)
    navigation_layout: str = "sidebar"
    must_change_password: bool = False

    class Config:
        from_attributes = True
