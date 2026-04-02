from src.models.exceptions import NegativeValidationError


class PositiveNumber:
    def __init__(self, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return getattr(instance, self.name)

    def __set__(self, instance, value):
        if value < 0:
            raise NegativeValidationError(f"{self.name} не может быть отрицательным")
        setattr(instance, self.name, value)


class NotNull:
    def __init__(self, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return getattr(instance, self.name)

    def __set__(self, instance, value):
        if value is None:
            raise AttributeError(f"{self.name} не может быть пустым")
        setattr(instance, self.name, value)


class EmailDescriptor:
    def __init__(self, email):
        self.email = email

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return getattr(instance, self.email)

    def __set__(self, instance, value):
        if "@" not in value:
            raise AttributeError(f"{self.email} не верный формат")
        setattr(instance, self.email, value)


class AgeDescriptor:
    def __init__(self, age):
        self.age = age

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return getattr(instance, self.age)

    def __set__(self, instance, value):
        if value < 18:
            raise AttributeError(f"{self.age} Пользователь не может быть моложе 18 лет")
        setattr(instance, self.age, value)


class CachedProperty:
    def __init__(self, func):
        self.func = func
        self.name = func.__name__

    def __get__(self, instance, owner):
        if instance is None:
            return self

        cache_attr = f"_cached_{self.name}"
        if hasattr(instance, cache_attr):
            return getattr(instance, cache_attr)

        value = self.func(instance)
        setattr(instance, cache_attr, value)
        return value
