# infrastructure/postgres

- Таблицы — пакет `tables/`: один модуль на агрегат (`users.py`, `api_tokens.py`, ...), общий `metadata`
  с naming convention в `tables/base.py`. Новый модуль обязательно импортируется в `tables/__init__.py`,
  иначе alembic его не увидит.
- Маппинг доменных сущностей — imperative, все `map_imperatively` в `mapping.py`; domain про SQLAlchemy не знает.
  Папка не называется `models/`: ORM-моделей тут нет, модели живут в domain.
- Енамы — колонки `String`, без CHECK-constraint и `native_enum` (ADR 0004).
- Деревья читаются рекурсивными CTE в `readers/`; неактивные ветки отсекаются внутри рекурсии.
  Обязательны индексы `(owner_id, parent_id)` у папок и `(owner_id, folder_id)` у задач.
- Каждый запрос фильтруется по владельцу — но решение о доступе принимает `AccessPolicy`, а не репозиторий.
- Транзакцией управляет сервис через порт `TransactionManager`; репозитории не вызывают `commit()`.

## Миграции

- Только `alembic revision --autogenerate`, затем обязательно прочитать и поправить сгенерированный файл.
- Применённую (смёрженную в main) миграцию не редактировать — только новая.
- Каждая миграция должна иметь рабочий `downgrade()`.
