import subprocess

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


def api_error(status: int, detail: str, code: str) -> HTTPException:
    return HTTPException(status, {"detail": detail, "code": code})


def describe(exc: BaseException) -> str:
    """A message a creator can act on, instead of a raw exception string."""
    from google.genai import errors as genai_errors  # local: keep errors.py import-light

    from app.services.llm import LLMQuotaError

    if isinstance(exc, LLMQuotaError):
        return "The AI service is out of quota right now. Try again later or add a backup API key."
    if isinstance(exc, genai_errors.APIError):
        return f"The AI service returned an error ({exc.code}). Try again in a minute."
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) or "timed out" in str(exc).lower():
        return "A step took too long and was stopped. Try again; shorter footage processes faster."
    if isinstance(exc, FileNotFoundError) and "ffmpeg" in str(exc).lower():
        return "FFmpeg is not installed on the server."
    return str(exc) or exc.__class__.__name__


async def llm_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": describe(exc), "code": "LLM_ERROR"}, status_code=502)


async def llm_quota_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "The AI service is out of quota right now. Try again later or add a backup API key.",
                         "code": "LLM_QUOTA_EXCEEDED"}, status_code=503)


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Flatten errors to {detail, code} per API_ENDPOINTS.md."""
    body = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail, "code": "HTTP_ERROR"}
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)
