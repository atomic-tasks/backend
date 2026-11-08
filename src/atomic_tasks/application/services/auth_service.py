from atomic_tasks.application.dto import AuthMethod, Identity
from atomic_tasks.application.errors import AuthenticationError
from atomic_tasks.application.ports.oidc import TokenVerifier
from atomic_tasks.application.services.identity_service import IdentityService
from atomic_tasks.application.services.token_service import TokenService
from atomic_tasks.domain.entities.api_token import TokenScope, looks_like_api_token


class AuthService:
    """Единая точка аутентификации для FastAPI и MCP: заголовок Authorization → Identity.

    `at_...` — personal access token; всё остальное проверяется как JWT от IdP.
    """

    def __init__(
        self,
        tokens: TokenService,
        verifier: TokenVerifier,
        identities: IdentityService,
    ) -> None:
        self._tokens = tokens
        self._verifier = verifier
        self._identities = identities

    async def authenticate(self, authorization: str | None) -> Identity:
        credentials = _bearer(authorization)
        if credentials is None:
            raise AuthenticationError
        if looks_like_api_token(credentials):
            return await self._tokens.authenticate(credentials)
        claims = await self._verifier.verify(credentials)
        user = await self._identities.resolve(claims)
        return Identity(user_id=user.id, scope=TokenScope.WRITE, method=AuthMethod.SESSION)


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        return None
    return credentials.strip()
