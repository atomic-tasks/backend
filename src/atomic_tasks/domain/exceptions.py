class DomainError(Exception):
    """Нарушение бизнес-правила.

    Текст увидит пользователь или агент — он должен объяснять, что исправить.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UserDisabledError(DomainError):
    def __init__(self) -> None:
        super().__init__("Аккаунт отключён.")


class TokenLimitExceededError(DomainError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"Не больше {limit} активных токенов. Отзовите неиспользуемые.")


class InvalidTokenParamsError(DomainError):
    pass


class InsufficientScopeError(DomainError):
    def __init__(self, required: str) -> None:
        super().__init__(f"Токену не хватает прав: нужен scope '{required}'.")
