from abc import ABC, abstractmethod

from loguru import logger


class Notification(ABC):
    @abstractmethod
    async def send(self, message: str) -> str:
        pass


class EmailNotification(Notification):
    async def send(self, message: str) -> str:
        logger.info(f"Email: {message}")
        return f"Email: {message}"


class SMSNotification(Notification):
    async def send(self, message: str) -> str:
        return f"SMS: {message}"


async def send_notification(send_type: Notification, message: str):
    await send_type.send(message)
