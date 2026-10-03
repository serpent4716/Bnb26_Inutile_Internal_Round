from datetime import timedelta

import bcrypt
import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db import db
from app.errors import api_error
from app.models.common import utcnow

TOKEN_TTL = timedelta(days=7)
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "exp": utcnow() + TOKEN_TTL}, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> str:
    """Return the user id, or raise jwt.PyJWTError on a bad/expired token."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])["sub"]


async def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    unauthorized = api_error(401, "Not authenticated", "UNAUTHORIZED")
    if cred is None:
        raise unauthorized
    try:
        user_id = ObjectId(decode_token(cred.credentials))
    except (jwt.PyJWTError, InvalidId):
        raise unauthorized
    user = await db.users.find_one({"_id": user_id})
    if user is None:
        raise unauthorized
    return user
