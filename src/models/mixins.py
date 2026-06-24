import json


class LoggableMixin:
    def log(self, message):
        class_name = self.__class__.__name__
        print(f"[{class_name}] {message}")


class SerializableMixin:
    def to_dict(self):
        return self.__dict__

    def to_json(self):
        return json.dumps(self.to_dict(), indent=4, ensure_ascii=False)