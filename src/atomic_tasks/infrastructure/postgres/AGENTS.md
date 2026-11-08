# infrastructure/postgres

- Таблицы описываются в `tables.py` через общий `metadata` (с naming convention).
  Маппинг доменных сущностей — imperative (`mapper_registry.map_imperatively`), domain про SQLAlchemy не знает.
- Енамы — колонки `String`, без CHECK-constraint и `native_enum` (ADR 0004).
- Деревья читаются рекурсивными CTE в `readers/`; неактивные ветки отсекаются внутри рекурсии.
  Обязательны индексы `(owner_id, parent_id)` у папок и `(owner_id, folder_id)` у задач.
- Каждый запрос фильтруется по владельцу — но решение о доступе принимает `AccessPolicy`, а не репозиторий.
- Транзакцией управляет сервис через порт `TransactionManager`; репозитории не вызывают `commit()`.

## Миграции

- Только `alembic revision --autogenerate`, затем обязательно прочитать и поправить сгенерированный файл.
- Применённую (смёрженную в main) миграцию не редактировать — только новая.
- Каждая миграция должна иметь рабочий `downgrade()`.
