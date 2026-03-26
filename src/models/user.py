class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email

        try:
            if "@" not in email:
                raise ValueError("Неверный формат email")
        except ValueError as e:
            print(e)

    def get_info(self) -> str:
        return f"Пользователь: {self.name}, Email: {self.email}"

    def __str__(self):
        return self.name
