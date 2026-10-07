from typing import ClassVar
from pydantic import BaseModel, model_validator


class Base(BaseModel):
    pass


class PatchBase(Base):
    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        nulls = sorted(
            name for name in self.model_fields_set - self.nullable_fields
            if getattr(self, name) is None
        )
        if nulls:
            raise ValueError(f"Поля не могут быть null: {', '.join(nulls)}")
        return self
