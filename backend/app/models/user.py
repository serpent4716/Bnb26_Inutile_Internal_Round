from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.common import MongoModel


class User(MongoModel):
    name: str
    email: EmailStr
    password_hash: str | None = Field(default=None, exclude=True)
    niche: str = ""
    tone_profile: str = ""
    connected_platforms: list[str] = []
    created_at: datetime | None = None


class RegisterIn(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt limit
    niche: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str
