from enum import StrEnum

from atomic_tasks.domain.exceptions import DomainError


class ApplicationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthenticationError(ApplicationError):
    """Нет учётных данных или они недействительны → 401."""

    def __init__(self, message: str = "Требуется действительный токен.") -> None:
        super().__init__(message)


class PermissionDeniedError(ApplicationError):
    """Аутентифицирован, но действие запрещено → 403."""


class NotFoundError(ApplicationError):
    """Объекта нет или он чужой — не различаем, чтобы не раскрывать существование → 404."""

    def __init__(self, what: str = "Объект") -> None:
        super().__init__(f"{what} не найден.")


class InvalidQueryError(ApplicationError):
    """Неверные параметры запроса (limit, пустой набор статусов, слишком большая пачка) → 400."""


class BulkItemError(ApplicationError):
    """Ошибка одного элемента пачки: адрес элемента + текст исходной ошибки.

    Пачка атомарна, поэтому агенту важно знать, какой элемент исправить, чтобы повторить её целиком.
    """

    def __init__(self, address: str, cause: ApplicationError | DomainError) -> None:
        super().__init__(f"{address}: {cause.message}")
        self.address = address
        self.cause = cause


class LoginFailure(StrEnum):
    """Почему не удался вход через браузер. Уходит в `/?login_error=<код>`, деталей наружу нет."""

    ACCESS_DENIED = "access_denied"  # allowlist, пользователь отключён, отказ в IdP
    EXPIRED = "expired"  # вход просрочен или уже завершён
    FAILED = "failed"  # подделка state, ошибка IdP, недействительный id_token


class LoginFailedError(ApplicationError):
    def __init__(self, code: LoginFailure) -> None:
        super().__init__("Вход не удался.")
        self.code = code
