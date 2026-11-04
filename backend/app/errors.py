"""Consistent JSON error envelope + handlers.

Every error response looks like:
    {"error": {"code": "...", "message": "...", "request_id": "...", "details": ...}}
"""
from __future__ import annotations

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import get_logger

log = get_logger("errors")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(
    status_code: int, code: str, message: str, request: Request, details: object | None = None
) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message}}
    rid = _request_id(request)
    if rid:
        body["error"]["request_id"] = rid
    if details is not None:
        body["error"]["details"] = jsonable_encoder(details)
    return JSONResponse(status_code=status_code, content=body)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return error_response(exc.status_code, "http_error", str(exc.detail), request)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(422, "validation_error", "Request validation failed", request, exc.errors())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", path=request.url.path, exc_info=exc)
    return error_response(500, "internal_error", "An unexpected error occurred", request)


def register_error_handlers(app) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
