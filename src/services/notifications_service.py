from abc import ABC, abstractmethod


class Notification(ABC):
    @abstractmethod
    async def send(self, message: str) -> str:
        pass


class EmailNotification(Notification):
    async def send(self, message: str) -> str:
        return f"Email: {message}"


class SMSNotification(Notification):
    async def send(self, message: str) -> str:
        return f"SMS: {message}"


def send_notification(send_type: Notification, message: str):
    send_type.send(message)