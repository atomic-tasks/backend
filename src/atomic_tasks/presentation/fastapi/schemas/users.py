from uuid import UUID

from pydantic import BaseModel


class MeResponse(BaseModel):
    id: UUID
    display_name: str
    email: str | None
