from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, status

from atomic_tasks.application.services.token_service import TokenService
from atomic_tasks.presentation.fastapi.auth import CurrentIdentity
from atomic_tasks.presentation.fastapi.schemas.tokens import (
    CreatedTokenResponse,
    CreateTokenRequest,
    TokenResponse,
)

router = APIRouter(prefix="/tokens", tags=["tokens"], route_class=DishkaRoute)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_token(
    body: CreateTokenRequest,
    identity: CurrentIdentity,
    tokens: FromDishka[TokenService],
) -> CreatedTokenResponse:
    identity.require_session()
    created = await tokens.create(
        user_id=identity.user_id,
        name=body.name,
        scope=body.scope,
        ttl_days=body.expires_in_days,
    )
    return CreatedTokenResponse(
        **TokenResponse.from_info(created.info).model_dump(), token=created.token
    )


@router.get("")
async def list_tokens(
    identity: CurrentIdentity, tokens: FromDishka[TokenService]
) -> list[TokenResponse]:
    identity.require_session()
    return [TokenResponse.from_info(info) for info in await tokens.list_for_user(identity.user_id)]


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: UUID,
    identity: CurrentIdentity,
    tokens: FromDishka[TokenService],
) -> None:
    identity.require_session()
    await tokens.revoke(user_id=identity.user_id, token_id=token_id)
