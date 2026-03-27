class User:
    def __init__(self, name: str, email: str):
        self.name = name
        self._email = email
        if "@" not in email:
            raise ValueError("Неверный формат email")

    def __str__(self):
        return self.name

    def get_info(self) -> str:
        return f"Пользователь: {self.name}, Email: {self._email}"

    def get_email(self) -> str:
        return self._email

    def set_email(self, email: str):
        if "@" not in email:
            raise ValueError("Неверный формат email")
        else:
            self._email = email
