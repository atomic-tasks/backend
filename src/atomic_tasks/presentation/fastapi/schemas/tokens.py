from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from atomic_tasks.application.dto import TokenInfo
from atomic_tasks.domain.entities.api_token import (
    DEFAULT_TTL_DAYS,
    MAX_NAME_LENGTH,
    MAX_TTL_DAYS,
    TokenScope,
)


class CreateTokenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    scope: TokenScope = TokenScope.WRITE
    expires_in_days: int | None = Field(
        default=DEFAULT_TTL_DAYS,
        ge=1,
        le=MAX_TTL_DAYS,
        description="null — бессрочный токен.",
    )


class TokenResponse(BaseModel):
    id: UUID
    name: str
    prefix: str
    scope: TokenScope
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def from_info(cls, info: TokenInfo) -> TokenResponse:
        return cls(**info.__dict__)


class CreatedTokenResponse(TokenResponse):
    token: str = Field(description="Показывается один раз.")
