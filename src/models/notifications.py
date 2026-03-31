from abc import ABC, abstractmethod


class Notification(ABC):
    @abstractmethod
    def send(self, message: str) -> str:
        pass


class EmailNotification(Notification):
    def send(self, message: str) -> str:
        return f"Email: {message}"


class SMSNotification(Notification):
    def send(self, message: str) -> str:
        return f"SMS: {message}"


def send_notification(send_type: Notification, message: str):
    send_type.send(message)
