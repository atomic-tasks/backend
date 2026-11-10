import argparse
import asyncio
import sys
from pathlib import Path

from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings
from atomic_tasks.infrastructure.postgres.mapping import map_entities
from atomic_tasks.presentation.cli import run


def _export_openapi(argv: list[str]) -> int:
    from atomic_tasks.config.openapi import export_openapi  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="python -m atomic_tasks openapi",
        description="Вывести OpenAPI-схему (без БД и без .env).",
    )
    parser.add_argument("--output", type=Path, help="файл вместо stdout, например openapi.json")
    args = parser.parse_args(argv)
    schema = export_openapi()
    if args.output is None:
        sys.stdout.write(schema)
    else:
        args.output.write_text(schema, encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    # Экспорту схемы не нужны ни БД, ни настройки окружения — разбираем до создания контейнера.
    if argv[:1] == ["openapi"]:
        return _export_openapi(argv[1:])

    map_entities()

    async def _run() -> int:
        container = create_container(Settings())
        try:
            return await run(container, argv)
        finally:
            await container.close()

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
