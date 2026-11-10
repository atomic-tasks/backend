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
    """Неверные параметры чтения (limit, пустой набор статусов) → 400."""
