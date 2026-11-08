import sys

import uvicorn


def main() -> None:
    if len(sys.argv) > 1:
        from atomic_tasks.config.cli import main as cli_main  # noqa: PLC0415

        sys.exit(cli_main(sys.argv[1:]))
    uvicorn.run("atomic_tasks.config.app:create_app", factory=True, host="0.0.0.0", port=8000)  # noqa: S104


if __name__ == "__main__":
    main()
