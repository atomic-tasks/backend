"""Экспорт OpenAPI-схемы — контракта для клиентов (спека 0005)."""

import json

from atomic_tasks.config.app import create_app
from atomic_tasks.config.settings import Settings


def export_openapi() -> str:
    """Схема ровно та, что отдаёт сервер на /openapi.json, но не зависит от окружения.

    Issuer IdP попадает в схему (authorizationUrl), поэтому .env и переменные окружения
    игнорируются: model_construct() берёт только значения по умолчанию. Иначе файл в репозитории
    менялся бы от машины к машине. К БД ничего не подключается — контейнер создаётся лениво.
    """
    app = create_app(Settings.model_construct())
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
