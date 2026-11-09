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


# Тексты ошибок ниже видит агент. Названия папок и задач в них не подставляем:
# это данные пользователя, а не инструкции.


class InvalidFieldError(DomainError):
    pass


class RootFolderProtectedError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Корневую папку нельзя удалить, перенести, переименовать или сменить ей вес и статус.",
        )


class FolderCycleError(DomainError):
    def __init__(self) -> None:
        super().__init__("Нельзя перенести папку в саму себя или в свою вложенную папку.")


class FolderNotActiveError(DomainError):
    def __init__(self, status: str) -> None:
        super().__init__(
            f"Папка в статусе '{status}': создавать и переносить в неё можно, "
            "только когда она 'active'.",
        )


class FolderHasOpenItemsError(DomainError):
    def __init__(self, folders: int, tasks: int) -> None:
        super().__init__(
            f"Нельзя отметить папку выполненной: внутри открыто папок — {folders}, "
            f"задач — {tasks}. Завершите или отмените их, либо поставьте папке "
            "'paused' или 'cancelled'.",
        )


class FolderNotEmptyError(DomainError):
    def __init__(self, folders: int, tasks: int) -> None:
        super().__init__(
            f"Папка не пуста: подпапок — {folders}, задач — {tasks}. "
            "Чтобы удалить её вместе с содержимым, передайте recursive=true.",
        )


class DoneAncestorError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Нельзя открыть: папка выше по дереву выполнена (done). "
            "Сначала откройте её или перенесите элемент в активную папку.",
        )
