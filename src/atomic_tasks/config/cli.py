import asyncio
import sys

from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings
from atomic_tasks.infrastructure.postgres.mapping import map_entities
from atomic_tasks.presentation.cli import run


def main(argv: list[str]) -> int:
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
