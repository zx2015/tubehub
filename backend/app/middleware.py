"""全局异常处理中间件

详见 docs/design/06-error-handling.md §6.1
"""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import FastAPI

from loguru import logger


async def global_exception_handler(request: Request, exc: Exception):
    """捕获所有未处理异常，避免栈跟踪泄露。"""
    logger.exception(
        f"Unhandled error: {request.method} {request.url.path} - {exc}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "code": "TUBEHUB_INTERNAL_ERROR",
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 校验失败统一格式。"""
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "code": "TUBEHUB_VALIDATION_ERROR",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理到 FastAPI app。"""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
