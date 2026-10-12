from dataclasses import dataclass
from typing import Any, Literal

from sfmshop.database.models import User


@dataclass(frozen=True)
class Actor:
    id: int
    role: Literal["user", "admin"]

    @classmethod
    def of(cls, user: User) -> "Actor":
        return cls(user.id, "admin" if user.is_admin else "user")

    def event_fields(self) -> dict[str, Any]:
        return {"actor_id": self.id, "actor_role": self.role}
