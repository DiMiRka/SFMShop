import json
from abc import ABC, abstractmethod


class LoggableMixin:
    def log(self, message: str):
        print(f"[{self.__class__.__name__}] {message}")


class ValidatableMixin(ABC):
    @abstractmethod
    def validate(self):
        pass


class SerializableMixin:
    def to_json(self):
        return json.dumps(self.__dict__)
