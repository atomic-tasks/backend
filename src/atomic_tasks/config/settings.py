from functools import cached_property

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresSettings(BaseModel):
    host: str = "localhost"
    port: int = 5432
    user: str = "atomic_tasks"
    password: SecretStr = SecretStr("atomic_tasks")
    db: str = "atomic_tasks"
    echo: bool = False

    @property
    def dsn(self) -> str:
        password = self.password.get_secret_value()
        return f"postgresql+asyncpg://{self.user}:{password}@{self.host}:{self.port}/{self.db}"


class McpSettings(BaseModel):
    # Значения заголовка Host, с которых принимаются MCP-запросы (защита от DNS rebinding).
    # В проде сюда добавляется публичный домен.
    allowed_hosts: list[str] = ["localhost:*", "127.0.0.1:*"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    debug: bool = False
    postgres: PostgresSettings = PostgresSettings()
    mcp: McpSettings = McpSettings()

    @cached_property
    def version(self) -> str:
        from importlib.metadata import version  # noqa: PLC0415

        return version("atomic-tasks")
