from src.schemas.base import Base


class Token(Base):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(Base):
    user_id: int
