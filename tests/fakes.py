"""Подмены внешних систем для тестов."""

from urllib.parse import urlencode

from dishka import Provider, Scope, provide

from atomic_tasks.application.dto import AuthTarget
from atomic_tasks.application.errors import AuthenticationError
from atomic_tasks.application.ports.oidc import OidcClient, TokenVerifier, VerifiedClaims

FAKE_ISSUER = "https://idp.test/auth/v1"


class FakeTokenVerifier:
    """Принимает «JWT» вида `jwt:<sub>:<email>` — без IdP, но через тот же путь в AuthService."""

    async def verify(self, raw: str, *, target: AuthTarget) -> VerifiedClaims:
        marker, _, rest = raw.partition(":")
        subject, _, email = rest.partition(":")
        if marker != "jwt" or not subject:
            raise AuthenticationError
        return VerifiedClaims(
            issuer=FAKE_ISSUER,
            subject=subject,
            email=email or None,
            email_verified=True,
            name=None,
        )


class FakeIdpProvider(Provider):
    @provide(scope=Scope.APP, override=True)
    def verifier(self) -> TokenVerifier:
        return FakeTokenVerifier()


class FakeOidcClient:
    """Вход через браузер без IdP: code — это `<sub>:<email>`, nonce возвращается как есть.

    Authorize URL несёт state, чтобы тест мог «вернуться» на callback как браузер.
    """

    async def authorization_url(
        self, *, state: str, code_challenge: str, nonce: str, redirect_uri: str
    ) -> str:
        return f"https://idp.test/authorize?{urlencode({'state': state, 'nonce': nonce})}"

    async def exchange_code(
        self, *, code: str, code_verifier: str, nonce: str, redirect_uri: str
    ) -> VerifiedClaims:
        subject, _, email = code.partition(":")
        if not subject or subject == "bad":
            raise AuthenticationError
        return VerifiedClaims(
            issuer=FAKE_ISSUER,
            subject=subject,
            email=email or None,
            email_verified=True,
            name=None,
        )


class FakeOidcClientProvider(Provider):
    @provide(scope=Scope.APP, override=True)
    def oidc_client(self) -> OidcClient:
        return FakeOidcClient()
