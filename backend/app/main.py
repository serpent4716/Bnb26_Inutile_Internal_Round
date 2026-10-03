import logging
import shutil
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db import create_indexes, ping
from app.errors import http_error_handler, llm_quota_handler
from app.routers import assets, auth, clips, generate, insights, processing, projects, scripts
from app.services.auth import get_current_user
from app.services.llm import LLMQuotaError
from app.services.storage import MEDIA_DIR

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if await ping():
        await create_indexes()
        log.info("MongoDB connected, indexes ensured")
    else:
        log.error("MongoDB unreachable, check MONGODB_URI in .env")
    yield


app = FastAPI(title="CreatorAi API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(LLMQuotaError, llm_quota_handler)

api = APIRouter(prefix="/api/v1")


@api.get("/health")
async def health():
    return {"db": "ok" if await ping() else "down", "ffmpeg": shutil.which("ffmpeg") is not None}


api.include_router(auth.router)
for r in (assets, scripts, projects, processing, clips, generate, insights):
    api.include_router(r.router, dependencies=[Depends(get_current_user)])

app.include_router(api)
# ponytail: local media is public by URL (a <video> tag can't send a bearer token); signed URLs if that matters
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
