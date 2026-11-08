from atomic_tasks.application.dto import Identity
from atomic_tasks.application.errors import AuthenticationError
from atomic_tasks.application.services.token_service import TokenService


class AuthService:
    """Единая точка аутентификации для FastAPI и MCP: значение заголовка Authorization → Identity.

    Сейчас только PAT; проверка JWT от IdP добавится вместе с Rauthy.
    """

    def __init__(self, tokens: TokenService) -> None:
        self._tokens = tokens

    async def authenticate(self, authorization: str | None) -> Identity:
        credentials = _bearer(authorization)
        if credentials is None:
            raise AuthenticationError
        return await self._tokens.authenticate(credentials)


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        return None
    return credentials.strip()
