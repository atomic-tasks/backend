"""Подмены внешних систем для тестов."""

from dishka import Provider, Scope, provide

from atomic_tasks.application.dto import AuthTarget
from atomic_tasks.application.errors import AuthenticationError
from atomic_tasks.application.ports.oidc import TokenVerifier, VerifiedClaims

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
