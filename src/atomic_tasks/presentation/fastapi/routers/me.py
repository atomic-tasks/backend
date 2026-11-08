from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.presentation.fastapi.auth import CurrentIdentity
from atomic_tasks.presentation.fastapi.schemas.users import MeResponse

router = APIRouter(tags=["users"], route_class=DishkaRoute)


@router.get("/me")
async def get_me(identity: CurrentIdentity, users: FromDishka[UserService]) -> MeResponse:
    user = await users.get(identity.user_id)
    return MeResponse(id=user.id, display_name=user.display_name, email=user.email)
