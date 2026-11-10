from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from atomic_tasks.application.errors import (
    ApplicationError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
)
from atomic_tasks.domain.exceptions import (
    DomainError,
    DoneAncestorError,
    FolderCycleError,
    FolderHasOpenItemsError,
    FolderNotActiveError,
    FolderNotEmptyError,
    InsufficientScopeError,
    RootFolderProtectedError,
    TokenLimitExceededError,
    UserDisabledError,
)

_STATUS: list[tuple[type[Exception], int]] = [
    (AuthenticationError, 401),
    (PermissionDeniedError, 403),
    (UserDisabledError, 403),
    (InsufficientScopeError, 403),
    (NotFoundError, 404),
    (TokenLimitExceededError, 409),
    # Состояние дерева не позволяет действие: запрос верный, мешает текущее состояние.
    (RootFolderProtectedError, 409),
    (FolderCycleError, 409),
    (FolderNotActiveError, 409),
    (FolderHasOpenItemsError, 409),
    (FolderNotEmptyError, 409),
    (DoneAncestorError, 409),
    (DomainError, 422),
    (ApplicationError, 400),
]


def problem(status: int, detail: str) -> JSONResponse:
    """Ответ об ошибке в формате RFC 9457 (problem details)."""
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None  # noqa: PLR2004
    return JSONResponse(
        {"type": "about:blank", "status": status, "detail": detail},
        status_code=status,
        media_type="application/problem+json",
        headers=headers,
    )


def status_for(exc: Exception) -> int:
    return next(status for cls, status in _STATUS if isinstance(exc, cls))


async def _handle(_: Request, exc: Exception) -> JSONResponse:
    message = exc.message if isinstance(exc, DomainError | ApplicationError) else str(exc)
    return problem(status_for(exc), message)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle)
    app.add_exception_handler(ApplicationError, _handle)
