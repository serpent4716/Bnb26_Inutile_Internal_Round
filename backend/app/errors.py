from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


def api_error(status: int, detail: str, code: str) -> HTTPException:
    return HTTPException(status, {"detail": detail, "code": code})


async def llm_quota_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "The AI service is out of quota right now. Try again later or add a backup API key.",
                         "code": "LLM_QUOTA_EXCEEDED"}, status_code=503)


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Flatten errors to {detail, code} per API_ENDPOINTS.md."""
    body = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail, "code": "HTTP_ERROR"}
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)
