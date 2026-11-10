from typing import Protocol


class TransactionManager(Protocol):
    async def commit(self) -> None: ...

    async def flush(self) -> None:
        """Отправляет накопленные изменения в базу без commit.

        Нужен пачкам: следующий шаг проверяет правило SQL-запросом и должен видеть предыдущие.
        """
        ...
