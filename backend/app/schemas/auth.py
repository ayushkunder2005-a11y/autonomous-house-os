from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserRead(ORMModel):
    id: str
    email: EmailStr
    display_name: str
    house_id: str | None
    is_active: bool
    role_name: str
    permissions: list[str]


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    role: str = "member"
    house_id: str | None = None
    security_pin: str | None = Field(default=None, min_length=4, max_length=12)


class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)
