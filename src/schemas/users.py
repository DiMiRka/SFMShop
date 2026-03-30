from src.schemas.base import Base


class UserCreate(Base):
    name: str
    email: str
