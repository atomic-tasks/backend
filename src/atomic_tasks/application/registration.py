from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class RegistrationPolicy:
    """Кого пускать при первом входе через IdP. Пустой allowlist — регистрация закрыта."""

    allowed_emails: frozenset[str]

    def allows(self, email: str | None, *, email_verified: bool) -> bool:
        return email is not None and email_verified and email.lower() in self.allowed_emails
