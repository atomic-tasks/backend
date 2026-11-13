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
    # Публичный адрес /mcp ровно так, как его вводят в коннектор (https://<API_HOST>/mcp).
    # Включает OAuth для коннекторов: метаданные ресурса (RFC 9728) и токены с этим aud (ADR 0012).
    # Пусто — выключено, /mcp принимает только PAT и токены наших клиентов.
    resource_url: str | None = None
    # client_id (URL CIMD-документа) клиентов, которым можно в MCP; запись на "/" — префикс.
    # Rauthy выдаёт код любому CIMD-клиенту без экрана согласия — чужих отсекаем здесь (ADR 0012).
    # Документы проверены 2026-11-13, таблица — docs/specs/0007-claude-connector-oauth/spec.md.
    trusted_clients: list[str] = [
        "https://claude.ai/oauth/mcp-oauth-client-metadata",  # Claude: веб, desktop, мобильный
        "https://claude.ai/oauth/claude-code-client-metadata",
        "https://chatgpt.com/oauth/client.json",
        "https://chatgpt.com/oauth/codex/client.json",
        "https://vscode.dev/oauth/client-metadata.json",  # VS Code и Copilot в нём
        "https://github.com/copilot/cli/client-metadata.json",
        "https://cursor.com/oauth/mcp-client.json",
        "https://zed.dev/oauth/client-metadata.json",
        "https://antigravity.google/oauth/client-metadata.json",
        "https://accountlinking.google.com/clientidmetadata/",  # Gemini custom connected apps
    ]


class AuthSettings(BaseModel):
    # Issuer IdP ровно как в claim iss токена. У Rauthy — <pub_url>/auth/v1/ со слешем на конце.
    issuer: str = "http://localhost:8080/auth/v1/"
    # Допустимые значения aud: client id наших приложений в IdP. Пусто — вход через IdP выключен.
    audience: list[str] = []
    # Адрес IdP изнутри Docker-сети (например http://rauthy:8080), если issuer оттуда недоступен.
    internal_url: str | None = None
    # Кого пускать при первом входе через IdP. Пусто — регистрация закрыта.
    allowed_emails: list[str] = []
    # Клиент IdP для входа в Swagger /docs (public, PKCE).
    swagger_client_id: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    debug: bool = False
    postgres: PostgresSettings = PostgresSettings()
    mcp: McpSettings = McpSettings()
    auth: AuthSettings = AuthSettings()

    @cached_property
    def version(self) -> str:
        from importlib.metadata import version  # noqa: PLC0415

        return version("atomic-tasks")
