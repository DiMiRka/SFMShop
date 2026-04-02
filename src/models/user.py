from dataclasses import dataclass, field

from src.models.metaclasses import ModelMeta
from src.models.mixins import SerializableMixin, LoggableMixin
from src.models.descriptors import EmailDescriptor, PositiveNumber, NotNull, AgeDescriptor


@dataclass
class User(LoggableMixin, SerializableMixin, metaclass=ModelMeta):
    id: int = PositiveNumber('id')
    name: str = NotNull("name")
    email: str = EmailDescriptor("_email")
    age: int = AgeDescriptor("age")
    balance: int = PositiveNumber("balance")
    orders: list = field(default_factory=list)
    is_active: bool = True

    def __post_init__(self):
        self.log(f"Создан: {self.name}")

    def __str__(self):
        return self.name

    def get_info(self) -> str:
        return f"Пользователь: {self.name}, Email: {self.email}"
