from fastapi import APIRouter, Depends
from pymongo.errors import DuplicateKeyError

from app.db import db
from app.errors import api_error
from app.models.common import utcnow
from app.models.user import LoginIn, RegisterIn, TokenOut, User
from app.services.auth import create_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(body: RegisterIn):
    doc = {
        "name": body.name,
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "niche": body.niche,
        "tone_profile": "",
        "connected_platforms": [],
        "created_at": utcnow(),
    }
    try:
        res = await db.users.insert_one(doc)
    except DuplicateKeyError:
        raise api_error(409, "Email already registered", "EMAIL_TAKEN")
    return {"token": create_token(str(res.inserted_id))}


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise api_error(401, "Invalid email or password", "INVALID_CREDENTIALS")
    return {"token": create_token(str(user["_id"]))}


@router.get("/me", response_model=User)
async def me(user: dict = Depends(get_current_user)):
    return user
