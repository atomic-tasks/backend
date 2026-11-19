import secrets
import uuid
from dataclasses import dataclass

from atomic_tasks.application.dto import LoginResult, LoginStart
from atomic_tasks.application.errors import (
    AuthenticationError,
    LoginFailedError,
    LoginFailure,
    PermissionDeniedError,
)
from atomic_tasks.application.ports.browser_sessions import (
    BrowserSessionRepository,
    LoginAttemptRepository,
)
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.ports.oidc import OidcClient
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.services.identity_service import IdentityService
from atomic_tasks.domain.entities.browser_session import (
    IDLE_TTL,
    LOGIN_TTL,
    BrowserSession,
    LoginAttempt,
    generate_secret,
    pkce_challenge,
    safe_return_to,
)
from atomic_tasks.domain.exceptions import UserDisabledError
from atomic_tasks.domain.secrets import hash_secret

IDP_ACCESS_DENIED = "access_denied"  # RFC 6749 §4.1.2.1: пользователь отказался


@dataclass(frozen=True, kw_only=True)
class WebLoginConfig:
    redirect_uri: str  # <WEB__ORIGIN>/api/v1/auth/callback


class BrowserLoginService:
    """Вход через браузер (BFF, ADR 0013): бэкенд сам проходит вход в IdP и заводит свою сессию."""

    def __init__(  # noqa: PLR0917 — зависимости внедряет dishka
        self,
        attempts: LoginAttemptRepository,
        sessions: BrowserSessionRepository,
        oidc: OidcClient,
        identities: IdentityService,
        tx: TransactionManager,
        clock: Clock,
        config: WebLoginConfig,
    ) -> None:
        self._attempts = attempts
        self._sessions = sessions
        self._oidc = oidc
        self._identities = identities
        self._tx = tx
        self._clock = clock
        self._config = config

    async def start(self, return_to: str | None) -> LoginStart:
        now = self._clock.now()
        state, verifier, nonce = generate_secret(), generate_secret(), generate_secret()
        url = await self._oidc.authorization_url(
            state=state,
            code_challenge=pkce_challenge(verifier),
            nonce=nonce,
            redirect_uri=self._config.redirect_uri,
        )
        # Вход не требует аутентификации: чистим просроченные попытки и здесь, чтобы брошенные
        # входы не копились дольше LOGIN_TTL.
        await self._attempts.delete_expired(now)
        self._attempts.add(
            LoginAttempt(
                id=uuid.uuid7(),
                state_hash=hash_secret(state),
                code_verifier=verifier,
                nonce=nonce,
                return_to=safe_return_to(return_to),
                expires_at=now + LOGIN_TTL,
            ),
        )
        await self._tx.commit()
        return LoginStart(redirect_url=url, state=state)

    async def finish(
        self,
        *,
        state_cookie: str | None,
        state: str | None,
        code: str | None,
        idp_error: str | None,
    ) -> LoginResult:
        """Callback от IdP. Любая неудача — LoginFailedError с кодом для сайта."""
        if idp_error:
            denied = idp_error == IDP_ACCESS_DENIED
            raise LoginFailedError(LoginFailure.ACCESS_DENIED if denied else LoginFailure.FAILED)
        if not state_cookie:
            # Cookie входа живёт 10 минут; нет её — вход просрочен или начат на другом хосте
            raise LoginFailedError(LoginFailure.EXPIRED)
        if (
            not state
            or not code
            or not secrets.compare_digest(state_cookie.encode(), state.encode())
        ):
            raise LoginFailedError(LoginFailure.FAILED)

        now = self._clock.now()
        attempt = await self._attempts.pop_by_state_hash(hash_secret(state))
        await self._tx.commit()  # попытка сгорает до обмена кода: повтор callback не пройдёт
        if attempt is None or attempt.is_expired(now):
            raise LoginFailedError(LoginFailure.EXPIRED)

        try:
            claims = await self._oidc.exchange_code(
                code=code,
                code_verifier=attempt.code_verifier,
                nonce=attempt.nonce,
                redirect_uri=self._config.redirect_uri,
            )
        except AuthenticationError as exc:
            raise LoginFailedError(LoginFailure.FAILED) from exc
        try:
            user = await self._identities.resolve(claims)
        except (PermissionDeniedError, UserDisabledError) as exc:
            raise LoginFailedError(LoginFailure.ACCESS_DENIED) from exc

        secret = generate_secret()
        self._sessions.add(
            BrowserSession.new(
                id=uuid.uuid7(), user_id=user.id, token_hash=hash_secret(secret), now=now
            ),
        )
        await self._sessions.delete_expired(now=now, idle_before=now - IDLE_TTL)
        await self._attempts.delete_expired(now)
        await self._tx.commit()
        return LoginResult(session_secret=secret, return_to=attempt.return_to)

    async def logout(self, secret: str | None) -> None:
        if not secret:
            return
        await self._sessions.delete_by_hash(hash_secret(secret))
        await self._tx.commit()
