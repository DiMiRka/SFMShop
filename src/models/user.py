class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email
        if "@" not in email:
            raise ValueError("Неверный формат email")

    def get_info(self) -> str:
        return f"Пользователь: {self.name}, Email: {self.email}"

    def __str__(self):
        return self.name
